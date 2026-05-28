"""javis.py — JAVIS Voice Recorder

시스템 마이크를 인식하고 음성을 녹음하여 WAV 파일로 저장한다.
파일명 형식: YYYYMMDD-HHMMSS.wav  (예: 20260528-143052.wav)
저장 위치: 실행 파일 하위 records/ 폴더
"""

import os
import wave
import datetime

try:
    import sounddevice as sd
    import numpy as np
except ImportError as exc:
    print(f'필요한 라이브러리가 설치되지 않았습니다: {exc}')
    print('설치 명령: pip install sounddevice numpy')
    raise SystemExit(1)

# ------------------------------------------------------------------ #
# 상수                                                                 #
# ------------------------------------------------------------------ #

SAMPLE_RATE = 44100   # 샘플링 주파수 (Hz)
CHANNELS = 1          # 채널 수 (1=모노)
SAMPLE_WIDTH = 2      # 샘플 크기 (바이트, 16-bit PCM)
RECORDS_DIR = 'records'


# ------------------------------------------------------------------ #
# JavisRecorder 클래스                                                 #
# ------------------------------------------------------------------ #

class JavisRecorder:
    """마이크 음성을 녹음하고 WAV 파일로 저장하는 클래스.

    sounddevice 의 InputStream 콜백 방식으로 오디오를 실시간 수집하며,
    녹음 중지 시 float32 데이터를 16-bit PCM 으로 변환하여 저장한다.
    """

    def __init__(self):
        self._sample_rate = SAMPLE_RATE
        self._channels = CHANNELS
        self._audio_data = []
        self._stream = None
        self._is_recording = False
        self._records_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), RECORDS_DIR
        )
        self._ensure_records_dir()

    # ---- 내부 헬퍼 ------------------------------------------------- #

    def _ensure_records_dir(self):
        """records 폴더가 없으면 생성한다."""
        try:
            os.makedirs(self._records_dir, exist_ok=True)
        except OSError as exc:
            print(f'[오류] records 폴더 생성 실패: {exc}')
            raise SystemExit(1)

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice 스트림 콜백.

        오디오 프레임이 준비될 때마다 호출되며,
        데이터를 내부 버퍼에 누적한다.
        """
        if status:
            print(f'  [경고] 오디오 상태: {status}')
        self._audio_data.append(indata.copy())

    def _save_recording(self):
        """버퍼에 저장된 오디오 데이터를 WAV 파일로 저장한다.

        파일명은 현재 날짜·시간을 기반으로 생성한다.
        성공 시 저장 경로(str)를, 실패 시 None 을 반환한다.
        """
        now = datetime.datetime.now()
        filename = now.strftime('%Y%m%d-%H%M%S') + '.wav'
        filepath = os.path.join(self._records_dir, filename)

        try:
            # float32 (-1.0 ~ 1.0) 를 int16 으로 변환
            audio = np.concatenate(self._audio_data, axis=0)
            audio_int16 = (
                np.clip(audio * 32767, -32768, 32767).astype(np.int16)
            )

            with wave.open(filepath, 'wb') as wav_file:
                wav_file.setnchannels(self._channels)
                wav_file.setsampwidth(SAMPLE_WIDTH)
                wav_file.setframerate(self._sample_rate)
                wav_file.writeframes(audio_int16.tobytes())

            print(f'저장 완료: {filename}')
            return filepath

        except (OSError, ValueError) as exc:
            print(f'[오류] 파일 저장 실패: {exc}')
            return None

    # ---- 공개 프로퍼티 --------------------------------------------- #

    @property
    def is_recording(self):
        """현재 녹음 중이면 True 를 반환한다."""
        return self._is_recording

    # ---- 장치 관련 ------------------------------------------------- #

    def get_input_devices(self):
        """사용 가능한 입력 장치 목록을 반환한다.

        Returns
        -------
        list of (int, str)
            (장치 인덱스, 장치 이름) 튜플의 리스트
        """
        devices = sd.query_devices()
        return [
            (idx, device['name'])
            for idx, device in enumerate(devices)
            if device['max_input_channels'] > 0
        ]

    # ---- 녹음 제어 ------------------------------------------------- #

    def start_recording(self, device=None):
        """녹음을 시작한다.

        Parameters
        ----------
        device : int or None
            사용할 입력 장치 인덱스. None 이면 시스템 기본 장치를 사용한다.
        """
        if self._is_recording:
            print('이미 녹음 중입니다.')
            return

        self._audio_data = []

        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype='float32',
                device=device,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_recording = True
            print('녹음을 시작했습니다. 중지하려면 Enter 를 누르세요.')

        except sd.PortAudioError as exc:
            print(f'[오류] 마이크를 열 수 없습니다: {exc}')
            self._stream = None

    def stop_recording(self):
        """녹음을 중지하고 파일을 저장한다.

        Returns
        -------
        str or None
            저장된 파일의 전체 경로. 녹음 중이 아니거나 실패 시 None.
        """
        if not self._is_recording:
            print('녹음 중이 아닙니다.')
            return None

        try:
            self._stream.stop()
            self._stream.close()
        except sd.PortAudioError as exc:
            print(f'[경고] 스트림 종료 중 오류: {exc}')
        finally:
            self._stream = None
            self._is_recording = False

        if not self._audio_data:
            print('녹음된 데이터가 없습니다.')
            return None

        return self._save_recording()

    # ---- 파일 목록 ------------------------------------------------- #

    def list_recordings(self):
        """records 폴더의 WAV 파일 목록을 정렬하여 반환한다.

        Returns
        -------
        list of str
            파일명 목록 (오름차순 정렬)
        """
        try:
            return sorted(
                f for f in os.listdir(self._records_dir)
                if f.endswith('.wav')
            )
        except OSError as exc:
            print(f'[오류] 목록 조회 실패: {exc}')
            return []

    def list_recordings_by_date_range(self, start_date, end_date):
        """지정한 날짜 범위에 해당하는 WAV 파일 목록을 반환한다.

        파일명의 앞 8자리(YYYYMMDD)를 날짜로 파싱하여 비교한다.
        형식에 맞지 않는 파일명은 건너뛴다.

        Parameters
        ----------
        start_date : datetime.date
        end_date   : datetime.date

        Returns
        -------
        list of str
        """
        result = []
        for filename in self.list_recordings():
            try:
                date_str = filename[:8]
                file_date = datetime.datetime.strptime(
                    date_str, '%Y%m%d'
                ).date()
                if start_date <= file_date <= end_date:
                    result.append(filename)
            except (ValueError, IndexError):
                continue
        return result


# ------------------------------------------------------------------ #
# CLI 헬퍼 함수                                                        #
# ------------------------------------------------------------------ #

def select_device(recorder):
    """사용자에게 입력 장치를 선택하도록 안내하고 선택된 장치 ID 를 반환한다.

    Enter 를 그냥 누르면 시스템 기본 장치를 사용한다.
    """
    devices = recorder.get_input_devices()
    if not devices:
        print('사용 가능한 마이크가 없습니다.')
        return None

    default_id = sd.default.device[0]
    print('\n사용 가능한 마이크 목록:')
    for idx, name in devices:
        marker = ' ← 기본값' if idx == default_id else ''
        print(f'  {idx:2}. {name}{marker}')

    raw = input('\n사용할 마이크 번호 (Enter: 기본값): ').strip()

    if not raw:
        return None

    try:
        device_id = int(raw)
        valid_ids = {idx for idx, _ in devices}
        if device_id not in valid_ids:
            print('목록에 없는 번호입니다. 기본 마이크를 사용합니다.')
            return None
        return device_id
    except ValueError:
        print('숫자를 입력해야 합니다. 기본 마이크를 사용합니다.')
        return None


def parse_date(prompt):
    """사용자에게 날짜(YYYYMMDD)를 입력받아 datetime.date 객체로 반환한다."""
    while True:
        raw = input(prompt).strip()
        try:
            return datetime.datetime.strptime(raw, '%Y%m%d').date()
        except ValueError:
            print('날짜 형식이 올바르지 않습니다. 예: 20260528')


def format_filename(filename):
    """YYYYMMDD-HHMMSS.wav 형태의 파일명을 읽기 쉬운 문자열로 변환한다."""
    try:
        base = filename.replace('.wav', '')
        date_part, time_part = base.split('-')
        return (
            f'{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} '
            f'{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}'
        )
    except (ValueError, IndexError):
        return filename


def print_recording_list(files):
    """녹음 파일 목록을 번호와 함께 출력한다."""
    if not files:
        print('해당하는 녹음 파일이 없습니다.')
        return

    print(f'\n총 {len(files)}개의 녹음 파일:')
    for i, filename in enumerate(files, 1):
        readable = format_filename(filename)
        print(f'  {i:3}. {filename}  ({readable})')


def print_menu(is_recording):
    """현재 상태에 따른 메인 메뉴를 출력한다."""
    status = ' [● 녹음 중]' if is_recording else ''
    print(f'\n─────────────────────────────{status}')
    print(' 1. 마이크 선택')
    print(' 2. 녹음 시작')
    print(' 3. 녹음 중지 및 저장')
    print(' 4. 전체 녹음 목록')
    print(' 5. 날짜 범위로 검색  [보너스]')
    print(' 0. 종료')
    print('─────────────────────────────')


# ------------------------------------------------------------------ #
# 진입점                                                               #
# ------------------------------------------------------------------ #

def main():
    """JAVIS 음성 녹음기 메인 루프."""
    print('==============================================')
    print('   JAVIS Voice Recorder  — 화성 음성 일기장')
    print('==============================================')

    recorder = JavisRecorder()
    selected_device = None

    while True:
        print_menu(recorder.is_recording)
        choice = input('선택: ').strip()

        if choice == '1':
            selected_device = select_device(recorder)
            if selected_device is not None:
                devices = dict(recorder.get_input_devices())
                print(f'선택된 마이크: {devices.get(selected_device, "??")}')
            else:
                print('기본 마이크를 사용합니다.')

        elif choice == '2':
            recorder.start_recording(device=selected_device)

        elif choice == '3':
            recorder.stop_recording()

        elif choice == '4':
            files = recorder.list_recordings()
            print_recording_list(files)

        elif choice == '5':
            print('\n날짜 범위를 입력하세요 (형식: YYYYMMDD)')
            start = parse_date('시작 날짜: ')
            end = parse_date('종료 날짜: ')
            if start > end:
                print('[오류] 시작 날짜가 종료 날짜보다 늦습니다.')
            else:
                files = recorder.list_recordings_by_date_range(start, end)
                print(
                    f'\n{start} ~ {end} 범위 검색 결과:'
                )
                print_recording_list(files)

        elif choice == '0':
            if recorder.is_recording:
                print('녹음을 먼저 중지합니다...')
                recorder.stop_recording()
            print('JAVIS 를 종료합니다.')
            break

        else:
            print('올바른 메뉴 번호를 선택하세요.')


if __name__ == '__main__':
    main()
