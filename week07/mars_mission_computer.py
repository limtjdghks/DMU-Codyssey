import os
import platform
import time
import threading
from datetime import datetime

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    print('[WARNING] psutil not installed. System load info will be unavailable.')

LOG_FILE_NAME = 'mars_sensor_log.txt'
MAX_LOG_SIZE = 10 * 1024 * 1024
SETTING_FILE = 'setting.txt'

SAFE_RANGES = {
    'mars_base_internal_temperature': (18.0, 30.0),
    'mars_base_external_temperature': (-60.0, 50.0),
    'mars_base_internal_humidity': (40.0, 70.0),
    'mars_base_external_illuminance': (0.0, 1000.0),
    'mars_base_internal_co2': (0.0, 0.08),
    'mars_base_internal_oxygen': (19.5, 23.5),
}


def _script_dir():
    normalized = __file__.replace('\\', '/')
    if '/' in normalized:
        return normalized.rsplit('/', 1)[0]
    return '.'


def _log_file_path():
    return f'{_script_dir()}/{LOG_FILE_NAME}'


def _setting_file_path():
    return f'{_script_dir()}/{SETTING_FILE}'


def _to_json(data, indent=4):
    """딕셔너리를 JSON 형태의 문자열로 변환한다."""
    lines = ['{']
    keys = list(data.keys())
    for i, key in enumerate(keys):
        value = data[key]
        comma = ',' if i < len(keys) - 1 else ''
        if isinstance(value, str):
            formatted_value = f'"{value}"'
        elif isinstance(value, bool):
            formatted_value = 'true' if value else 'false'
        else:
            formatted_value = str(value)
        lines.append(f'{" " * indent}"{key}": {formatted_value}{comma}')
    lines.append('}')
    return '\n'.join(lines)


def _load_settings():
    """setting.txt에서 출력할 항목 키 목록을 읽어온다.

    파일이 없거나 읽기 실패 시 None을 반환하여 전체 항목을 출력하도록 한다.
    # 으로 시작하는 줄은 주석으로 처리한다.
    """
    try:
        with open(_setting_file_path(), 'r', encoding='utf-8') as f:
            keys = set()
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    keys.add(stripped)
        return keys if keys else None
    except FileNotFoundError:
        return None
    except OSError as exc:
        print(f'[WARNING] Failed to read setting.txt: {exc}')
        return None


def _filter_by_settings(data):
    """setting.txt에 정의된 항목만 필터링하여 반환한다.

    setting.txt가 없거나 읽기 실패 시 원본 데이터를 그대로 반환한다.
    """
    allowed = _load_settings()
    if allowed is None:
        return data
    return {k: v for k, v in data.items() if k in allowed}


class DummySensor:
    """화성 기지의 환경 센서를 시뮬레이션하는 더미 센서 클래스.

    실제 센서 대신 의사 난수로 환경값을 생성한다.
    """

    def __init__(self):
        self.env_values = {
            'mars_base_internal_temperature': 0.0,
            'mars_base_external_temperature': 0.0,
            'mars_base_internal_humidity': 0.0,
            'mars_base_external_illuminance': 0.0,
            'mars_base_internal_co2': 0.0,
            'mars_base_internal_oxygen': 0.0,
        }
        self._counter = 0

    def _next_random(self, low, high, decimals=2):
        """LCG 알고리즘으로 low ~ high 범위의 의사 난수를 생성한다."""
        self._counter += 1
        timestamp = time.time()
        seed = int((timestamp * 1000000 + self._counter * 7919) % 2147483647)
        a = 1103515245
        c = 12345
        m = 2147483648
        seed = (seed * a + c) % m
        seed = (seed * a + c) % m
        value = seed / m
        result = low + value * (high - low)
        factor = 10 ** decimals
        return int(result * factor + 0.5) / factor

    def set_env(self):
        """각 센서에 해당하는 범위 내에서 무작위 환경값을 생성한다."""
        self.env_values['mars_base_internal_temperature'] = (
            self._next_random(18, 30, 2)
        )
        self.env_values['mars_base_external_temperature'] = (
            self._next_random(0, 21, 2)
        )
        self.env_values['mars_base_internal_humidity'] = (
            self._next_random(50, 60, 2)
        )
        self.env_values['mars_base_external_illuminance'] = (
            self._next_random(500, 715, 2)
        )
        self.env_values['mars_base_internal_co2'] = (
            self._next_random(0.02, 0.1, 4)
        )
        self.env_values['mars_base_internal_oxygen'] = (
            self._next_random(4, 7, 2)
        )

    def get_env(self):
        """현재 센서값을 반환하고 로그 파일에 타임스탬프와 함께 기록한다."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ev = self.env_values
        line = (
            f'{timestamp},'
            f"{ev['mars_base_internal_temperature']},"
            f"{ev['mars_base_external_temperature']},"
            f"{ev['mars_base_internal_humidity']},"
            f"{ev['mars_base_external_illuminance']},"
            f"{ev['mars_base_internal_co2']},"
            f"{ev['mars_base_internal_oxygen']}\n"
        )
        try:
            with open(_log_file_path(), 'a', encoding='utf-8') as log_file:
                log_file.write(line)
        except PermissionError:
            print(f'Error: permission denied writing log: {_log_file_path()}')
        except OSError as exc:
            print(f'Error: failed to write log: {_log_file_path()} ({exc})')

        return self.env_values


class MissionComputer:
    """화성 기지의 미션 컴퓨터 클래스.

    DummySensor로부터 환경 데이터를 수집하고 모니터링하며,
    컴퓨터 자체의 시스템 정보와 부하 상태를 진단한다.
    """

    def __init__(self):
        self.ds = DummySensor()
        self.env_values = {
            'mars_base_internal_temperature': 0.0,
            'mars_base_external_temperature': 0.0,
            'mars_base_internal_humidity': 0.0,
            'mars_base_external_illuminance': 0.0,
            'mars_base_internal_co2': 0.0,
            'mars_base_internal_oxygen': 0.0,
        }
        self._stop_flag = False
        self._paused = False
        self._history = []
        self._prev_values = None
        self._frozen_count = 0

    # ------------------------------------------------------------------ #
    # 시스템 정보 / 부하 진단                                              #
    # ------------------------------------------------------------------ #

    def get_mission_computer_info(self):
        """미션 컴퓨터의 시스템 정보를 수집하여 JSON 형식으로 출력한다.

        수집 항목: 운영체계, 운영체계 버전, CPU 타입, CPU 코어 수, 메모리 크기.
        setting.txt 가 존재하면 파일에 나열된 항목만 출력한다.
        각 항목 수집 시 예외가 발생하면 'Unavailable' 로 대체한다.
        """
        info = {}

        try:
            info['os'] = platform.system()
        except Exception as exc:
            info['os'] = f'Unavailable ({exc})'

        try:
            info['os_version'] = platform.version()
        except Exception as exc:
            info['os_version'] = f'Unavailable ({exc})'

        try:
            cpu_type = platform.processor()
            info['cpu_type'] = cpu_type if cpu_type else platform.machine()
        except Exception as exc:
            info['cpu_type'] = f'Unavailable ({exc})'

        try:
            cores = os.cpu_count()
            info['cpu_cores'] = cores if cores is not None else 'Unavailable'
        except Exception as exc:
            info['cpu_cores'] = f'Unavailable ({exc})'

        try:
            if not _PSUTIL_AVAILABLE:
                raise RuntimeError('psutil not installed')
            total_bytes = psutil.virtual_memory().total
            total_gb = round(total_bytes / (1024 ** 3), 2)
            info['memory_size'] = f'{total_gb} GB'
        except Exception as exc:
            info['memory_size'] = f'Unavailable ({exc})'

        print(_to_json(_filter_by_settings(info)))

    def get_mission_computer_load(self):
        """미션 컴퓨터의 실시간 CPU 및 메모리 사용량을 JSON 형식으로 출력한다.

        수집 항목: CPU 사용률(%), 메모리 사용률(%).
        setting.txt 가 존재하면 파일에 나열된 항목만 출력한다.
        각 항목 수집 시 예외가 발생하면 'Unavailable' 로 대체한다.
        """
        load = {}

        try:
            if not _PSUTIL_AVAILABLE:
                raise RuntimeError('psutil not installed')
            # interval=1 로 1초 동안 측정하여 정확한 사용률을 반환
            load['cpu_usage_percent'] = psutil.cpu_percent(interval=1)
        except Exception as exc:
            load['cpu_usage_percent'] = f'Unavailable ({exc})'

        try:
            if not _PSUTIL_AVAILABLE:
                raise RuntimeError('psutil not installed')
            load['memory_usage_percent'] = psutil.virtual_memory().percent
        except Exception as exc:
            load['memory_usage_percent'] = f'Unavailable ({exc})'

        print(_to_json(_filter_by_settings(load)))

    # ------------------------------------------------------------------ #
    # 센서 데이터 수집 (문제 6에서 이어받은 기능)                          #
    # ------------------------------------------------------------------ #

    def _listen_for_input(self):
        """별도 스레드에서 사용자 입력을 대기한다.

        'q': 시스템 종료 / 's': 일시정지·재개 토글
        """
        while not self._stop_flag:
            try:
                user_input = input().strip().lower()
                if user_input == 'q':
                    self._stop_flag = True
                elif user_input == 's':
                    if self._paused:
                        self._paused = False
                        print('Sensor data resumed.\n')
                    else:
                        self._paused = True
                        print('Sensor data paused.'
                              ' Enter "s" to resume, "q" to quit.\n')
            except EOFError:
                self._stop_flag = True
                break

    def _check_critical_values(self):
        """현재 센서값이 안전 범위를 벗어나는지 검사하고 경고를 출력한다."""
        for key, value in self.env_values.items():
            if key not in SAFE_RANGES:
                continue
            low, high = SAFE_RANGES[key]
            if value < low:
                print(f'  [WARNING] {key} = {value}'
                      f' (below safe minimum {low})')
            elif value > high:
                print(f'  [WARNING] {key} = {value}'
                      f' (above safe maximum {high})')

    def _check_sensor_frozen(self):
        """센서값이 3회 연속 동일하면 센서 고장 의심 경고를 출력한다."""
        if self._prev_values is None:
            self._prev_values = dict(self.env_values)
            return False

        if self.env_values == self._prev_values:
            self._frozen_count += 1
        else:
            self._frozen_count = 0

        self._prev_values = dict(self.env_values)

        if self._frozen_count >= 3:
            print('  [ALERT] Sensor values unchanged for 3+ cycles.'
                  ' Possible sensor malfunction!')
            return True
        return False

    def _manage_log_size(self):
        """로그 파일 크기가 MAX_LOG_SIZE를 초과하면 앞쪽 절반을 삭제한다."""
        try:
            with open(_log_file_path(), 'r', encoding='utf-8') as f:
                f.seek(0, 2)
                size = f.tell()
            if size > MAX_LOG_SIZE:
                with open(_log_file_path(), 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                half = len(lines) // 2
                with open(_log_file_path(), 'w', encoding='utf-8') as f:
                    f.writelines(lines[half:])
                print('  [INFO] Log file trimmed due to size limit.')
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f'  [ERROR] Log management failed: {exc}')

    def _print_average(self):
        """이력에 저장된 센서 데이터의 5분 평균값을 계산하여 출력한다."""
        if not self._history:
            return

        avg_values = {}
        keys = list(self._history[0].keys())
        for key in keys:
            total = sum(record[key] for record in self._history)
            avg_values[key] = round(total / len(self._history), 4)

        self._history.clear()

        print('\n===== 5-Minute Average =====')
        print(_to_json(avg_values))
        print('============================\n')

    def get_sensor_data(self):
        """센서 데이터를 5초 간격으로 수집하고 JSON 형태로 출력하는 메인 루프.

        's': 일시정지·재개 / 'q': 종료
        """
        print('Enter "q" to quit, "s" to pause/resume.\n')

        input_thread = threading.Thread(
            target=self._listen_for_input, daemon=True
        )
        input_thread.start()

        average_interval = 300
        elapsed_since_avg = 0
        log_check_interval = 60
        elapsed_since_log_check = 0

        try:
            while not self._stop_flag:
                if self._paused:
                    time.sleep(0.5)
                    continue

                self.ds.set_env()
                sensor_data = self.ds.get_env()

                if sensor_data is None:
                    print('  [ERROR] Sensor returned no data. Retrying...')
                    time.sleep(5)
                    continue

                self.env_values = dict(sensor_data)
                self._history.append(dict(self.env_values))

                print(_to_json(self.env_values))

                self._check_critical_values()
                self._check_sensor_frozen()

                elapsed_since_avg += 5
                elapsed_since_log_check += 5

                if elapsed_since_avg >= average_interval:
                    self._print_average()
                    elapsed_since_avg = 0

                if elapsed_since_log_check >= log_check_interval:
                    self._manage_log_size()
                    elapsed_since_log_check = 0

                time.sleep(5)
        except KeyboardInterrupt:
            pass

        print('System stoped....')


if __name__ == '__main__':
    runComputer = MissionComputer()

    print('===== Mission Computer Info =====')
    runComputer.get_mission_computer_info()
    print('=================================\n')

    print('===== Mission Computer Load =====')
    runComputer.get_mission_computer_load()
    print('=================================\n')

    runComputer.get_sensor_data()
