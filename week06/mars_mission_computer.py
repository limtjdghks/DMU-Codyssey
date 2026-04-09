import time
import threading
from datetime import datetime

# 로그 파일 이름 및 최대 크기 (10MB) 설정
LOG_FILE_NAME = 'mars_sensor_log.txt'
MAX_LOG_SIZE = 10 * 1024 * 1024

# 각 센서 항목별 안전 범위 정의 (최소값, 최대값)
# 이 범위를 벗어나면 경고 메시지를 출력한다
SAFE_RANGES = {
    'mars_base_internal_temperature': (18.0, 30.0),
    'mars_base_external_temperature': (-60.0, 50.0),
    'mars_base_internal_humidity': (40.0, 70.0),
    'mars_base_external_illuminance': (0.0, 1000.0),
    'mars_base_internal_co2': (0.0, 0.08),
    'mars_base_internal_oxygen': (19.5, 23.5),
}


def _log_file_path() -> str:
    """현재 스크립트 위치 기준으로 로그 파일의 절대 경로를 반환한다."""
    normalized = __file__.replace('\\', '/')
    if '/' in normalized:
        directory = normalized.rsplit('/', 1)[0]
        return f'{directory}/{LOG_FILE_NAME}'
    return LOG_FILE_NAME


def _to_json(data, indent=4):
    """딕셔너리를 JSON 형태의 문자열로 변환한다.
    별도 라이브러리 없이 직접 포맷팅한다.
    """
    lines = ['{']
    keys = list(data.keys())
    for i, key in enumerate(keys):
        value = data[key]
        comma = ',' if i < len(keys) - 1 else ''
        lines.append(f'{" " * indent}"{key}": {value}{comma}')
    lines.append('}')
    return '\n'.join(lines)


class DummySensor:
    """화성 기지의 환경 센서를 시뮬레이션하는 더미 센서 클래스.
    실제 센서 대신 의사 난수로 환경값을 생성한다.
    """

    def __init__(self) -> None:
        # 6가지 환경 센서값을 0.0으로 초기화
        self.env_values = {
            'mars_base_internal_temperature': 0.0,
            'mars_base_external_temperature': 0.0,
            'mars_base_internal_humidity': 0.0,
            'mars_base_external_illuminance': 0.0,
            'mars_base_internal_co2': 0.0,
            'mars_base_internal_oxygen': 0.0,
        }
        # 난수 생성 시 시드 다양성을 위한 호출 카운터
        self._counter = 0

    def _next_random(self, low, high, decimals=2):
        """LCG(선형 합동 생성기) 알고리즘으로 의사 난수를 생성한다.
        현재 시간과 호출 카운터를 시드로 사용하여
        low ~ high 범위의 실수를 반환한다.
        """
        self._counter += 1
        timestamp = time.time()
        # 시간 + 카운터를 조합하여 매번 다른 시드를 생성
        seed = int((timestamp * 1000000 + self._counter * 7919) % 2147483647)
        a = 1103515245
        c = 12345
        m = 2147483648
        # LCG 알고리즘을 2회 반복하여 무작위성 향상
        seed = (seed * a + c) % m
        seed = (seed * a + c) % m
        # 0~1 사이 값으로 정규화 후 원하는 범위로 변환
        value = seed / m
        result = low + value * (high - low)
        # 지정된 소수점 자릿수로 반올림
        factor = 10 ** decimals
        return int(result * factor + 0.5) / factor

    def set_env(self) -> None:
        """각 센서에 해당하는 범위 내에서 무작위 환경값을 생성하여 저장한다."""
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

    def get_env(self) -> dict:
        """현재 센서값을 반환하고, 로그 파일에 타임스탬프와 함께 기록한다."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ev = self.env_values
        # CSV 형식으로 한 줄 로그 생성
        line = (
            f'{timestamp},'
            f"{ev['mars_base_internal_temperature']},"
            f"{ev['mars_base_external_temperature']},"
            f"{ev['mars_base_internal_humidity']},"
            f"{ev['mars_base_external_illuminance']},"
            f"{ev['mars_base_internal_co2']},"
            f"{ev['mars_base_internal_oxygen']}\n"
        )
        # 로그 파일 쓰기 시 발생할 수 있는 예외 처리
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
    DummySensor로부터 환경 데이터를 수집하고 모니터링한다.
    """

    def __init__(self) -> None:
        # DummySensor를 ds라는 이름으로 인스턴스화
        self.ds = DummySensor()
        # 미션 컴퓨터가 관리하는 환경값 딕셔너리
        self.env_values = {
            'mars_base_internal_temperature': 0.0,
            'mars_base_external_temperature': 0.0,
            'mars_base_internal_humidity': 0.0,
            'mars_base_external_illuminance': 0.0,
            'mars_base_internal_co2': 0.0,
            'mars_base_internal_oxygen': 0.0,
        }
        self._stop_flag = False       # 시스템 종료 플래그
        self._paused = False           # 센서 데이터 일시정지 플래그
        self._history = []             # 5분 평균 계산을 위한 데이터 이력
        self._prev_values = None       # 센서 동결 감지를 위한 이전 값 저장
        self._frozen_count = 0         # 센서 값이 동일하게 반복된 횟수

    def _listen_for_input(self) -> None:
        """별도 스레드에서 사용자 입력을 대기하는 메소드.
        메인 루프를 블로킹하지 않고 키 입력을 감지한다.
        - 'q': 시스템 종료
        - 's': 일시정지 / 재개 토글
        """
        while not self._stop_flag:
            try:
                user_input = input().strip().lower()
                if user_input == 'q':
                    self._stop_flag = True
                elif user_input == 's':
                    # 's'를 누를 때마다 일시정지 상태를 토글
                    if self._paused:
                        self._paused = False
                        print('Sensor data resumed.\n')
                    else:
                        self._paused = True
                        print('Sensor data paused.'
                              ' Enter "s" to resume, "q" to quit.\n')
            except EOFError:
                # 입력 스트림이 닫힌 경우 안전하게 종료
                self._stop_flag = True
                break

    def _check_critical_values(self) -> None:
        """현재 센서값이 안전 범위(SAFE_RANGES)를 벗어나는지 검사한다.
        범위를 초과하면 경고 메시지를 출력한다.
        """
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

    def _check_sensor_frozen(self) -> bool:
        """센서값이 연속으로 동일한지 검사하여 센서 고장을 감지한다.
        3회 연속 같은 값이면 고장 의심 경고를 출력한다.
        """
        # 최초 호출 시 이전 값이 없으므로 현재 값을 저장만 한다
        if self._prev_values is None:
            self._prev_values = dict(self.env_values)
            return False

        # 현재 값과 이전 값을 비교하여 동결 횟수를 갱신
        if self.env_values == self._prev_values:
            self._frozen_count += 1
        else:
            self._frozen_count = 0

        self._prev_values = dict(self.env_values)

        # 3회 연속 동일하면 센서 고장 의심 경고
        if self._frozen_count >= 3:
            print('  [ALERT] Sensor values unchanged for 3+ cycles.'
                  ' Possible sensor malfunction!')
            return True
        return False

    def _manage_log_size(self) -> None:
        """로그 파일의 크기를 확인하고 MAX_LOG_SIZE 초과 시
        오래된 절반을 삭제하여 디스크 공간을 확보한다.
        """
        try:
            # 파일 끝으로 이동하여 크기를 확인
            with open(_log_file_path(), 'r', encoding='utf-8') as f:
                f.seek(0, 2)
                size = f.tell()
            # 최대 크기 초과 시 앞쪽 절반의 로그를 삭제
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

    def _print_average(self) -> None:
        """이력에 저장된 센서 데이터의 5분 평균값을 계산하여 출력한다.
        출력 후 이력을 초기화한다.
        """
        if not self._history:
            return

        avg_values = {}
        keys = list(self._history[0].keys())
        # 각 항목별로 전체 이력의 합계를 구해 평균 계산
        for key in keys:
            total = sum(record[key] for record in self._history)
            avg_values[key] = round(total / len(self._history), 4)

        # 평균 계산 후 이력 초기화
        self._history.clear()

        print('\n===== 5-Minute Average =====')
        print(_to_json(avg_values))
        print('============================\n')

    def get_sensor_data(self) -> None:
        """센서 데이터를 5초 간격으로 수집하고 JSON 형태로 출력하는 메인 루프.
        별도 스레드에서 사용자 입력을 감지하여
        일시정지(s), 종료(q) 기능을 제공한다.
        """
        print('Enter "q" to quit, "s" to pause/resume.\n')

        # 사용자 입력 감지를 위한 별도 스레드 시작
        # daemon=True로 설정하여 메인 프로그램 종료 시 스레드도 자동 종료
        input_thread = threading.Thread(
            target=self._listen_for_input, daemon=True
        )
        input_thread.start()

        average_interval = 300       # 5분(300초)마다 평균 출력
        elapsed_since_avg = 0        # 마지막 평균 출력 이후 경과 시간
        log_check_interval = 60      # 1분(60초)마다 로그 크기 확인
        elapsed_since_log_check = 0  # 마지막 로그 확인 이후 경과 시간

        try:
            while not self._stop_flag:
                # 일시정지 상태면 센서 데이터를 수집하지 않고 대기
                if self._paused:
                    time.sleep(0.5)
                    continue

                # 센서에 새로운 환경값을 생성하도록 요청
                self.ds.set_env()
                sensor_data = self.ds.get_env()

                # 센서가 데이터를 반환하지 못한 경우 재시도
                if sensor_data is None:
                    print('  [ERROR] Sensor returned no data. Retrying...')
                    time.sleep(5)
                    continue

                # 센서 데이터를 미션 컴퓨터의 env_values에 저장
                self.env_values = dict(sensor_data)

                # 5분 평균 계산을 위해 이력에 추가
                self._history.append(dict(self.env_values))

                # 현재 환경값을 JSON 형태로 출력
                print(_to_json(self.env_values))

                # 안전 범위 초과 여부 및 센서 고장 여부 검사
                self._check_critical_values()
                self._check_sensor_frozen()

                elapsed_since_avg += 5
                elapsed_since_log_check += 5

                # 5분마다 평균값 출력
                if elapsed_since_avg >= average_interval:
                    self._print_average()
                    elapsed_since_avg = 0

                # 1분마다 로그 파일 크기 확인 및 관리
                if elapsed_since_log_check >= log_check_interval:
                    self._manage_log_size()
                    elapsed_since_log_check = 0

                # 5초 대기 후 다음 센서 데이터 수집
                time.sleep(5)
        except KeyboardInterrupt:
            # Ctrl+C 입력 시에도 안전하게 종료
            pass

        print('System stoped....')


if __name__ == '__main__':
    # MissionComputer를 RunComputer라는 이름으로 인스턴스화하고
    # 센서 데이터 수집을 시작한다
    RunComputer = MissionComputer()
    RunComputer.get_sensor_data()
