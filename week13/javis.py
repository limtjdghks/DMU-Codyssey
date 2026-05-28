"""javis.py — JAVIS Voice Recorder & Transcriber

week12 의 음성 녹음 기능에 STT(Speech-to-Text) 기능을 추가한다.

녹음 파일명 형식: YYYYMMDD-HHMMSS.wav
CSV  파일명 형식: YYYYMMDD-HHMMSS.csv  (동일 이름, 확장자만 변경)
저장 위치: 실행 파일 하위 records/ 폴더

CSV 열 구성:
    시간(HH:MM:SS)  |  인식된 텍스트
"""

import csv
import os
import sys
import wave
import datetime
import warnings

# whisper / torch / numba 가 내부적으로 발생시키는 경고와
# tqdm 진행 바를 모두 억제하여 경고 없이 실행되도록 한다
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)
os.environ.setdefault('TQDM_DISABLE', '1')

try:
    import sounddevice as sd
    import numpy as np
except ImportError as exc:
    print(f'필요한 라이브러리가 설치되지 않았습니다: {exc}')
    print('설치 명령: pip install sounddevice numpy')
    raise SystemExit(1)

try:
    import whisper
except ImportError as exc:
    print(f'Whisper 가 설치되지 않았습니다: {exc}')
    print('설치 명령: pip install openai-whisper')
    raise SystemExit(1)

# ------------------------------------------------------------------ #
# 상수                                                                 #
# ------------------------------------------------------------------ #

SAMPLE_RATE = 44100   # 샘플링 주파수 (Hz)
CHANNELS = 1          # 채널 수 (1=모노)
SAMPLE_WIDTH = 2      # 샘플 크기 (바이트, 16-bit PCM)
RECORDS_DIR = 'records'

# ── Whisper 모델 설정 ──────────────────────────────────────────────
# tiny  : ~39 MB,  가장 빠름,  정확도 낮음
# base  : ~74 MB,  균형,       한국어 인식 크게 향상
# small : ~244 MB, 높은 정확도, tiny 대비 4~5배 느림
# medium: ~769 MB, 최고 정확도, 느린 환경 비권장
WHISPER_MODEL = 'base'

# 변환 시 Whisper 에 전달하는 파라미터
# initial_prompt: 한국어 문맥 힌트를 주어 인식률을 높인다
# beam_size     : 빔 탐색 폭 — 클수록 정확하나 느림 (기본 5)
# temperature   : 0 이면 그리디 디코딩(결정론적), 오류 시 자동 상승
# no_speech_threshold: 이 값 이하 확률의 구간은 무음으로 처리
WHISPER_OPTIONS = {
    'language': 'ko',
    'verbose': None,
    'beam_size': 5,
    'best_of': 5,
    'temperature': 0.0,
    'no_speech_threshold': 0.6,
    'compression_ratio_threshold': 2.4,
}

CSV_HEADER = ['시간', '인식된 텍스트']


# ------------------------------------------------------------------ #
# JavisRecorder 클래스 (week12 에서 이어받음)                           #
# ------------------------------------------------------------------ #

class JavisRecorder:
    """마이크 음성을 녹음하고 WAV 파일로 저장하는 클래스.

    sounddevice 의 InputStream 콜백 방식으로 오디오를 실시간 수집하며,
    녹음 중지 시 float32 데이터를 16-bit PCM 으로 변환하여 저장한다.
    """

    def __init__(self, records_dir):
        self._sample_rate = SAMPLE_RATE
        self._channels = CHANNELS
        self._audio_data = []
        self._stream = None
        self._is_recording = False
        self._records_dir = records_dir
        self._ensure_records_dir()

    def _ensure_records_dir(self):
        """records 폴더가 없으면 생성한다."""
        try:
            os.makedirs(self._records_dir, exist_ok=True)
        except OSError as exc:
            print(f'[오류] records 폴더 생성 실패: {exc}')
            raise SystemExit(1)

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice 스트림 콜백 — 오디오 프레임을 버퍼에 누적한다."""
        if status:
            print(f'  [경고] 오디오 상태: {status}')
        self._audio_data.append(indata.copy())

    def _save_recording(self):
        """버퍼의 오디오 데이터를 WAV 파일로 저장하고 경로를 반환한다."""
        now = datetime.datetime.now()
        filename = now.strftime('%Y%m%d-%H%M%S') + '.wav'
        filepath = os.path.join(self._records_dir, filename)

        try:
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

    @property
    def is_recording(self):
        """현재 녹음 중이면 True 를 반환한다."""
        return self._is_recording

    def get_input_devices(self):
        """사용 가능한 입력 장치 목록을 (인덱스, 이름) 튜플 리스트로 반환한다."""
        return [
            (idx, device['name'])
            for idx, device in enumerate(sd.query_devices())
            if device['max_input_channels'] > 0
        ]

    def start_recording(self, device=None):
        """지정 장치(또는 기본 장치)로 녹음을 시작한다."""
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
        """녹음을 중지하고 WAV 파일로 저장한다. 저장 경로 또는 None 반환."""
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

    def list_recordings(self):
        """records 폴더의 WAV 파일 목록을 오름차순으로 반환한다."""
        try:
            return sorted(
                f for f in os.listdir(self._records_dir)
                if f.endswith('.wav')
            )
        except OSError as exc:
            print(f'[오류] 목록 조회 실패: {exc}')
            return []

    def list_recordings_by_date_range(self, start_date, end_date):
        """지정한 날짜 범위(start_date ~ end_date)의 WAV 목록을 반환한다."""
        result = []
        for filename in self.list_recordings():
            try:
                file_date = datetime.datetime.strptime(
                    filename[:8], '%Y%m%d'
                ).date()
                if start_date <= file_date <= end_date:
                    result.append(filename)
            except (ValueError, IndexError):
                continue
        return result


# ------------------------------------------------------------------ #
# JavisTranscriber 클래스                                              #
# ------------------------------------------------------------------ #

class JavisTranscriber:
    """WAV 파일을 텍스트로 변환(STT)하고 CSV 로 저장하는 클래스.

    OpenAI Whisper 모델을 사용하며, 세그먼트별 시작 시간과 텍스트를
    CSV 파일에 기록한다. 모델은 최초 변환 시 한 번만 로드한다.
    """

    def __init__(self, records_dir, model_name=WHISPER_MODEL):
        self._records_dir = records_dir
        self._model_name = model_name
        self._model = None   # 지연 로딩: 실제 변환 직전에 로드

    # ---- 내부 헬퍼 ------------------------------------------------- #

    def _load_model(self):
        """Whisper 모델을 처음 한 번만 로드한다."""
        if self._model is None:
            print(f'Whisper 모델({self._model_name}) 로드 중...')
            self._model = whisper.load_model(self._model_name)
            print('모델 로드 완료.')

    @staticmethod
    def _seconds_to_timestamp(seconds):
        """float 초(seconds)를 HH:MM:SS 형식의 문자열로 변환한다."""
        total = int(seconds)
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        return f'{hours:02d}:{minutes:02d}:{secs:02d}'

    def _wav_path(self, wav_filename):
        return os.path.join(self._records_dir, wav_filename)

    def _csv_path(self, wav_filename):
        csv_name = wav_filename.replace('.wav', '.csv')
        return os.path.join(self._records_dir, csv_name)

    def _next_csv_path(self, wav_filename):
        """같은 WAV 에 대한 CSV 가 이미 존재하면 _2, _3 … 접미사를 붙여 반환한다.

        예) 20260528-143052.csv 가 있으면 20260528-143052_2.csv,
            그것도 있으면 20260528-143052_3.csv 를 반환한다.
        """
        base = wav_filename.replace('.wav', '')
        candidate = os.path.join(self._records_dir, base + '.csv')
        if not os.path.isfile(candidate):
            return candidate
        n = 2
        while True:
            candidate = os.path.join(self._records_dir, f'{base}_{n}.csv')
            if not os.path.isfile(candidate):
                return candidate
            n += 1

    # ---- 공개 메소드 ----------------------------------------------- #

    def transcribe_file(self, wav_filename):
        """단일 WAV 파일을 텍스트로 변환하고 세그먼트 목록을 반환한다.

        Parameters
        ----------
        wav_filename : str
            records 폴더 내 WAV 파일명 (경로 제외)

        Returns
        -------
        list of dict
            각 딕셔너리는 'start'(float, 초), 'end'(float, 초),
            'text'(str) 키를 포함한다.
            변환 실패 시 빈 리스트를 반환한다.
        """
        filepath = self._wav_path(wav_filename)
        if not os.path.isfile(filepath):
            print(f'[오류] 파일을 찾을 수 없습니다: {wav_filename}')
            return []

        self._load_model()
        print(f'변환 중: {wav_filename}  (모델: {self._model_name})')
        try:
            # tqdm 및 내부 진단 출력을 억제하기 위해 stderr 를 임시 차단한다
            _stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w', encoding='utf-8')
            try:
                result = self._model.transcribe(filepath, **WHISPER_OPTIONS)
            finally:
                sys.stderr.close()
                sys.stderr = _stderr

            segments = result.get('segments', [])
            cleaned = []
            for seg in segments:
                text = seg.get('text', '').strip()
                # 빈 텍스트 제거
                if not text:
                    continue
                # 무음 구간 제거 (no_speech_prob 임계값 초과)
                if seg.get('no_speech_prob', 0.0) >= WHISPER_OPTIONS['no_speech_threshold']:
                    continue
                cleaned.append(seg)
            return cleaned
        except Exception as exc:
            print(f'[오류] 변환 실패 ({wav_filename}): {exc}')
            return []

    def save_csv(self, wav_filename, segments):
        """세그먼트 목록을 CSV 파일로 저장하고 저장 경로를 반환한다.

        CSV 열: 시간(HH:MM:SS), 인식된 텍스트

        Parameters
        ----------
        wav_filename : str
        segments     : list of dict

        Returns
        -------
        str or None
        """
        if not segments:
            print(f'저장할 텍스트가 없습니다: {wav_filename}')
            return None

        csv_filepath = self._next_csv_path(wav_filename)
        try:
            with open(csv_filepath, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADER)
                for seg in segments:
                    timestamp = self._seconds_to_timestamp(seg['start'])
                    text = seg['text'].strip()
                    writer.writerow([timestamp, text])
            csv_name = os.path.basename(csv_filepath)
            print(f'CSV 저장 완료: {csv_name}  ({len(segments)}개 세그먼트)')
            return csv_filepath
        except OSError as exc:
            print(f'[오류] CSV 저장 실패: {exc}')
            return None

    def transcribe_and_save(self, wav_filename):
        """WAV 파일을 변환하고 결과를 CSV 로 저장한다.

        같은 WAV 에 대한 CSV 가 이미 존재하면 덮어쓰지 않고
        _2, _3 … 접미사를 붙인 새 파일로 저장한다.

        Returns
        -------
        str or None
            저장된 CSV 파일 경로. 실패 시 None.
        """
        segments = self.transcribe_file(wav_filename)
        return self.save_csv(wav_filename, segments)

    def transcribe_all(self, wav_list):
        """WAV 파일 목록 전체를 순서대로 변환하고 저장한다.

        Parameters
        ----------
        wav_list : list of str
        """
        if not wav_list:
            print('변환할 WAV 파일이 없습니다.')
            return

        print(f'\n총 {len(wav_list)}개 파일 변환을 시작합니다.')
        for i, wav_filename in enumerate(wav_list, 1):
            print(f'\n[{i}/{len(wav_list)}] ', end='')
            self.transcribe_and_save(wav_filename)

    def list_csv_files(self):
        """records 폴더의 CSV 파일 목록을 오름차순으로 반환한다."""
        try:
            return sorted(
                f for f in os.listdir(self._records_dir)
                if f.endswith('.csv')
            )
        except OSError as exc:
            print(f'[오류] CSV 목록 조회 실패: {exc}')
            return []

    def search_transcripts(self, keyword):
        """모든 CSV 파일에서 키워드를 검색하여 일치 행을 반환한다.

        대소문자를 구분하지 않고 검색한다.

        Parameters
        ----------
        keyword : str

        Returns
        -------
        list of dict
            각 딕셔너리: {'파일': str, '시간': str, '텍스트': str}
        """
        results = []
        keyword_lower = keyword.lower()

        for csv_filename in self.list_csv_files():
            csv_filepath = os.path.join(self._records_dir, csv_filename)
            try:
                with open(csv_filepath, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.reader(f)
                    next(reader, None)   # 헤더 건너뜀
                    for row in reader:
                        if len(row) < 2:
                            continue
                        if keyword_lower in row[1].lower():
                            results.append({
                                '파일': csv_filename,
                                '시간': row[0],
                                '텍스트': row[1],
                            })
            except OSError as exc:
                print(f'[경고] {csv_filename} 읽기 실패: {exc}')

        return results


# ------------------------------------------------------------------ #
# CLI 헬퍼 함수                                                        #
# ------------------------------------------------------------------ #

def select_device(recorder):
    """사용자에게 입력 장치를 선택하도록 안내하고 선택된 장치 ID 를 반환한다."""
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
        if device_id not in {idx for idx, _ in devices}:
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


def format_wav_filename(filename):
    """YYYYMMDD-HHMMSS.wav 형태의 파일명을 읽기 쉬운 문자열로 변환한다."""
    try:
        base = filename.replace('.wav', '').replace('.csv', '')
        date_part, time_part = base.split('-')
        return (
            f'{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} '
            f'{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}'
        )
    except (ValueError, IndexError):
        return filename


def print_wav_list(files):
    """녹음 파일 목록을 번호와 함께 출력한다."""
    if not files:
        print('해당하는 녹음 파일이 없습니다.')
        return
    print(f'\n총 {len(files)}개의 녹음 파일:')
    for i, filename in enumerate(files, 1):
        readable = format_wav_filename(filename)
        has_csv = filename.replace('.wav', '.csv')
        print(f'  {i:3}. {filename}  ({readable})', end='')
        print('  [변환완료]' if has_csv else '')


def print_search_results(results, keyword):
    """키워드 검색 결과를 출력한다."""
    if not results:
        print(f'"{keyword}" 에 해당하는 내용이 없습니다.')
        return
    print(f'\n"{keyword}" 검색 결과: 총 {len(results)}건')
    print('─' * 60)
    for item in results:
        readable = format_wav_filename(item['파일'])
        print(f'  파일: {item["파일"]}  ({readable})')
        print(f'  시간: {item["시간"]}')
        print(f'  내용: {item["텍스트"]}')
        print()


def select_wav_file(recorder):
    """WAV 파일 목록을 보여주고 사용자가 선택한 파일명을 반환한다."""
    files = recorder.list_recordings()
    if not files:
        print('records 폴더에 WAV 파일이 없습니다.')
        return None

    print_wav_list(files)
    raw = input('\n변환할 파일 번호 (Enter: 전체 변환): ').strip()

    if not raw:
        return '__ALL__'

    try:
        idx = int(raw) - 1
        if 0 <= idx < len(files):
            return files[idx]
        print('올바른 번호를 입력하세요.')
        return None
    except ValueError:
        print('숫자를 입력해야 합니다.')
        return None


def print_menu(is_recording):
    """메인 메뉴를 출력한다."""
    status = ' [● 녹음 중]' if is_recording else ''
    print(f'\n══════════════════════════════{status}')
    print(' 1. 마이크 선택')
    print(' 2. 녹음 시작')
    print(' 3. 녹음 중지 및 저장')
    print(' 4. 전체 녹음 목록')
    print(' 5. 날짜 범위로 녹음 검색')
    print(' 6. 음성 → 텍스트 변환 (STT)')
    print(' 7. 키워드 검색  [보너스]')
    print(' 0. 종료')
    print('══════════════════════════════')


# ------------------------------------------------------------------ #
# 진입점                                                               #
# ------------------------------------------------------------------ #

def main():
    """JAVIS 음성 녹음·변환기 메인 루프."""
    print('==============================================')
    print('  JAVIS Voice Recorder & Transcriber')
    print('  화성 음성 일기장  —  STT 버전')
    print('==============================================')

    records_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), RECORDS_DIR
    )

    recorder = JavisRecorder(records_dir)
    transcriber = JavisTranscriber(records_dir)
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
            print_wav_list(files)

        elif choice == '5':
            print('\n날짜 범위를 입력하세요 (형식: YYYYMMDD)')
            start = parse_date('시작 날짜: ')
            end = parse_date('종료 날짜: ')
            if start > end:
                print('[오류] 시작 날짜가 종료 날짜보다 늦습니다.')
            else:
                files = recorder.list_recordings_by_date_range(start, end)
                print(f'\n{start} ~ {end} 검색 결과:')
                print_wav_list(files)

        elif choice == '6':
            selected = select_wav_file(recorder)
            if selected == '__ALL__':
                transcriber.transcribe_all(recorder.list_recordings())
            elif selected:
                transcriber.transcribe_and_save(selected)

        elif choice == '7':
            keyword = input('검색할 키워드: ').strip()
            if keyword:
                results = transcriber.search_transcripts(keyword)
                print_search_results(results, keyword)
            else:
                print('키워드를 입력하세요.')

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
