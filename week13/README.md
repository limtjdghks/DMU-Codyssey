# JAVIS — 화성 음성 일기장 (Voice Recorder & Transcriber)

화성 기지에서 음성으로 일지를 남기고, 텍스트로 변환하여 검색할 수 있는 프로그램입니다.

---

## 목차

1. [채택 라이브러리](#1-채택-라이브러리)
2. [주요 설정값](#2-주요-설정값)
3. [음성 저장 로직](#3-음성-저장-로직)
4. [STT 변환 로직](#4-stt-변환-로직)
5. [결과물 — CSV 파일](#5-결과물--csv-파일)
6. [전체 흐름 요약](#6-전체-흐름-요약)

---

## 1. 채택 라이브러리

### 마이크 입력 — `sounddevice`

| 항목 | 내용 |
|---|---|
| 패키지 | `sounddevice` + `numpy` |
| 선택 이유 | PortAudio 기반으로 macOS·Windows·Linux 에서 동일하게 동작하며, **콜백 방식 스트리밍**으로 실시간 녹음이 가능하기 때문 |

---

### STT 변환 — `openai-whisper`

| 항목 | 내용 |
|---|---|
| 패키지 | `openai-whisper` (+ `torch`, `ffmpeg`) |
| 선택 이유 | **오프라인 동작**, 한국어 지원, **세그먼트 단위 타임스탬프** 제공 |

---

## 2. 주요 설정값

### 녹음 설정

```python
SAMPLE_RATE  = 44100  # 샘플링 주파수 (Hz) — CD 음질 수준
CHANNELS     = 1      # 모노 채널
SAMPLE_WIDTH = 2      # 16-bit PCM (2 바이트)
```

- `SAMPLE_RATE 44100` : 1초에 44,100번 샘플링. 사람 음성(300~3400 Hz)을 충분히 담을 수 있는 표준 CD 음질입니다.
- `CHANNELS 1` : 모노 녹음. 음성 인식에는 스테레오가 불필요하므로 파일 크기를 절반으로 줄입니다.
- `SAMPLE_WIDTH 2` : 샘플 하나를 2바이트(16-bit)로 저장하는 표준 WAV 포맷입니다.

---

### Whisper 모델

```python
# tiny  : ~39 MB,  가장 빠름,  정확도 낮음
# base  : ~74 MB,  균형,       한국어 인식 크게 향상  ← 현재 선택
# small : ~244 MB, 높은 정확도, tiny 대비 4~5배 느림
# medium: ~769 MB, 최고 정확도, 느린 환경 비권장
WHISPER_MODEL = 'base'
```

`tiny` 에서 `base` 로 업그레이드한 이유:
- 동일 하드웨어에서 처리 시간 차이가 크지 않음 (약 2배 이내)
- 한국어 인식 정확도가 크게 향상됨

---

### Whisper 변환 파라미터

```python
WHISPER_OPTIONS = {
    'language'                   : 'ko',  # 한국어 강제 지정 — 언어 감지 오류 방지
    'verbose'                    : None,  # 내부 진행 출력 완전 억제
    'beam_size'                  : 5,     # 빔 탐색 폭, 클수록 정확 (기본값 유지)
    'best_of'                    : 5,     # 후보 중 최적 결과 선택
    'temperature'                : 0.0,   # 결정론적 디코딩, 오류 시 자동 상승
    'no_speech_threshold'        : 0.6,   # 이 확률 초과 세그먼트는 무음으로 처리
    'compression_ratio_threshold': 2.4,   # 반복 패턴 감지 — 이상 출력 필터링
}
```

| 파라미터 | 역할 |
|---|---|
| `language: 'ko'` | 언어 자동 감지를 끄고 한국어로 고정. 짧은 발화에서 영어로 오인식하는 현상 방지 |
| `beam_size: 5` | 디코딩 시 동시에 탐색하는 후보 경로 수. 클수록 정확하지만 느려짐 |
| `temperature: 0.0` | 샘플링 없이 가장 확률 높은 토큰만 선택. 재현 가능한 결과를 보장 |
| `no_speech_threshold: 0.6` | 무음 확률이 60% 이상인 구간을 자동으로 제거 |
| `compression_ratio_threshold: 2.4` | 텍스트 압축률이 비정상적으로 높으면 반복 오류로 판단하고 제거 |

---

## 3. 음성 저장 로직

### 클래스: `JavisRecorder`

```
start_recording()
    │  sd.InputStream 을 열고 스트림 시작
    │  _audio_callback() 이 프레임마다 호출됨
    │
    ▼
[녹음 중 — 내부 버퍼(_audio_data)에 float32 프레임 누적]
    │
    ▼
stop_recording()
    │  스트림 정지 & 닫기
    │
    ▼
_save_recording()
    │  1. np.concatenate 로 버퍼 병합
    │  2. float32 → int16 변환
    │  3. wave 모듈로 WAV 파일 기록
    │
    ▼
records/YYYYMMDD-HHMMSS.wav 저장
```

---

### STEP 1 — 녹음 시작 & 콜백 버퍼 누적

```python
def start_recording(self, device=None):
    self._audio_data = []  # 버퍼 초기화

    self._stream = sd.InputStream(
        samplerate=self._sample_rate,  # 44100 Hz
        channels=self._channels,       # 1 (모노)
        dtype='float32',               # 콜백에서 받을 데이터 타입
        device=device,                 # None 이면 시스템 기본 마이크 사용
        callback=self._audio_callback, # 프레임마다 호출될 함수 등록
    )
    self._stream.start()
    self._is_recording = True
```

스트림이 시작되면 `sounddevice` 는 내부 스레드에서 `_audio_callback` 을 반복 호출합니다.

```python
def _audio_callback(self, indata, frames, time_info, status):
    if status:
        print(f'  [경고] 오디오 상태: {status}')
    self._audio_data.append(indata.copy())  # 프레임을 버퍼 뒤에 추가
```

`indata` 는 `(frames, channels)` shape 의 `float32` 배열입니다.
`.copy()` 를 호출하는 이유는 `indata` 가 내부 버퍼를 참조하는 뷰(view)이기 때문에, 다음 콜백 호출 시 덮어씌워지기 전에 복사해두어야 하기 때문입니다.

---

### STEP 2 — 녹음 중지 & WAV 저장

```python
def stop_recording(self):
    self._stream.stop()
    self._stream.close()
    self._is_recording = False
    return self._save_recording()
```

```python
def _save_recording(self):
    now = datetime.datetime.now()
    filename = now.strftime('%Y%m%d-%H%M%S') + '.wav'  # 파일명: 날짜-시간
    filepath = os.path.join(self._records_dir, filename)

    # ① 누적된 프레임 배열들을 하나로 병합
    audio = np.concatenate(self._audio_data, axis=0)

    # ② float32 (-1.0 ~ 1.0) → int16 (-32768 ~ 32767) 변환
    #    np.clip 으로 범위를 벗어난 값(클리핑)을 먼저 제한하고 캐스팅
    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)

    # ③ 표준 wave 모듈로 WAV 파일 저장
    with wave.open(filepath, 'wb') as wav_file:
        wav_file.setnchannels(self._channels)   # 채널 수 (1)
        wav_file.setsampwidth(SAMPLE_WIDTH)      # 샘플 크기 (2 바이트)
        wav_file.setframerate(self._sample_rate) # 샘플링 주파수 (44100)
        wav_file.writeframes(audio_int16.tobytes())

    return filepath
```

#### float32 → int16 변환이 필요한 이유

`sounddevice` 는 마이크 데이터를 **부동소수점(`float32`, -1.0 ~ 1.0)** 으로 반환합니다.
표준 WAV 파일(16-bit PCM)은 **정수(`int16`, -32768 ~ 32767)** 를 사용합니다.
`× 32767` 로 스케일링하고, `np.clip` 으로 오버플로를 막은 뒤 타입을 변환합니다.

#### 파일명 규칙

```
20260528-143052.wav
│         │
│         └─ 시간: 14시 30분 52초
└─────────── 날짜: 2026년 05월 28일
```

---

## 4. STT 변환 로직

### 클래스: `JavisTranscriber`

```
transcribe_and_save(wav_filename)
    │
    ▼
transcribe_file(wav_filename)
    │  ① 모델 지연 로딩
    │  ② model.transcribe() 호출
    │  ③ 세그먼트 필터링
    │
    ▼
save_csv(wav_filename, segments)
    │  _next_csv_path() 로 저장 경로 결정
    │  타임스탬프 변환 → CSV 행 기록
    │
    ▼
records/YYYYMMDD-HHMMSS.csv        ← 처음 변환
records/YYYYMMDD-HHMMSS_2.csv      ← 같은 파일 재변환 시
records/YYYYMMDD-HHMMSS_3.csv      ← 또 변환 시
```

---

### STEP 1 — 모델 지연 로딩

프로그램 시작 시가 아니라, **처음 변환을 요청하는 순간** 모델을 로드합니다.
약 74 MB 의 모델 파일을 불필요하게 매번 로드하지 않기 위한 지연(lazy) 로딩입니다.

```python
def __init__(self, records_dir, model_name=WHISPER_MODEL):
    self._model = None  # 아직 로드하지 않음

def _load_model(self):
    if self._model is None:  # 처음 호출될 때만 로드
        print(f'Whisper 모델({self._model_name}) 로드 중...')
        self._model = whisper.load_model(self._model_name)
        print('모델 로드 완료.')
```

---

### STEP 2 — 변환 실행

```python
def transcribe_file(self, wav_filename):
    self._load_model()  # 최초 1회만 실제 로드

    # tqdm 진행 바 / 내부 경고 출력을 stderr 차단으로 억제
    _stderr = sys.stderr
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    try:
        result = self._model.transcribe(filepath, **WHISPER_OPTIONS)
    finally:
        sys.stderr.close()
        sys.stderr = _stderr  # 반드시 복구
```

`model.transcribe()` 가 반환하는 `result['segments']` 는 아래와 같은 구조입니다.

```python
# 반환 예시
[
    {
        'start'         : 0.0,    # 발화 시작 시점 (초)
        'end'           : 3.2,    # 발화 종료 시점 (초)
        'text'          : '화성 기지 일지를 시작합니다',
        'no_speech_prob': 0.02,   # 무음일 확률 (0~1)
    },
    ...
]
```

---

### STEP 3 — 세그먼트 필터링

변환 결과에서 **2가지 기준**으로 불필요한 세그먼트를 제거합니다.

```python
cleaned = []

for seg in segments:
    text = seg.get('text', '').strip()

    # ① 빈 텍스트 제거
    if not text:
        continue

    # ② 무음 구간 제거 — no_speech_prob 가 임계값(0.6) 이상이면 무음
    if seg.get('no_speech_prob', 0.0) >= WHISPER_OPTIONS['no_speech_threshold']:
        continue

    cleaned.append(seg)
```

---

### STEP 4 — CSV 저장

```python
def save_csv(self, wav_filename, segments):
    csv_filepath = self._next_csv_path(wav_filename)  # 중복 시 _2, _3 … 접미사

    with open(csv_filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['시간', '인식된 텍스트'])  # 헤더

        for seg in segments:
            timestamp = self._seconds_to_timestamp(seg['start'])  # 초 → HH:MM:SS
            text = seg['text'].strip()
            writer.writerow([timestamp, text])
```

#### 타임스탬프 변환

Whisper 가 반환하는 `start` 는 float 초(seconds) 단위입니다.
이를 `HH:MM:SS` 형식으로 변환합니다.

```python
@staticmethod
def _seconds_to_timestamp(seconds):
    total   = int(seconds)
    hours   = total // 3600
    minutes = (total % 3600) // 60
    secs    = total % 60
    return f'{hours:02d}:{minutes:02d}:{secs:02d}'

# 예: 3725.0초 → 01:02:05
```

---

### 중복 변환 처리 — 번호 접미사

같은 WAV 파일을 다시 변환하면 기존 CSV 를 덮어쓰지 않고 번호 접미사를 붙인 새 파일로 저장합니다.

```python
def _next_csv_path(self, wav_filename):
    base = wav_filename.replace('.wav', '')

    candidate = os.path.join(self._records_dir, base + '.csv')
    if not os.path.isfile(candidate):   # 처음 변환이면 기본 이름 사용
        return candidate

    n = 2
    while True:                         # _2, _3 … 순서로 빈 이름 탐색
        candidate = os.path.join(self._records_dir, f'{base}_{n}.csv')
        if not os.path.isfile(candidate):
            return candidate
        n += 1
```

실행 예시:

```
20260528-143052.wav 를 처음 변환  →  20260528-143052.csv
같은 파일을 다시 변환             →  20260528-143052_2.csv
또 다시 변환                     →  20260528-143052_3.csv
```

---

### 키워드 검색

저장된 모든 CSV 파일을 열어 키워드가 포함된 행을 찾습니다.
대소문자를 구분하지 않고 검색합니다.

```python
def search_transcripts(self, keyword):
    results = []
    keyword_lower = keyword.lower()  # 소문자로 통일하여 대소문자 무관 비교

    for csv_filename in self.list_csv_files():
        csv_filepath = os.path.join(self._records_dir, csv_filename)

        with open(csv_filepath, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            next(reader, None)  # 헤더 행 건너뜀

            for row in reader:
                if len(row) < 2:
                    continue
                if keyword_lower in row[1].lower():  # 텍스트 열에서 검색
                    results.append({
                        '파일'  : csv_filename,
                        '시간'  : row[0],
                        '텍스트': row[1],
                    })

    return results
```

---

## 5. 결과물 — CSV 파일

### 저장 위치 및 파일명

```
records/
├── 20260528-143052.wav   ← 원본 음성
├── 20260528-143052.csv   ← 변환된 텍스트 (동일 이름, 확장자만 변경)
├── 20260528-180001.wav
└── 20260528-180001.csv
```

WAV 파일명과 CSV 파일명을 동일하게 맞춰, 어떤 음성에서 어떤 텍스트가 추출됐는지 한눈에 대응할 수 있습니다.

---

### CSV 구조

```
시간,인식된 텍스트
00:00:00,제하 모자를 우연히 발견한 건 39살이 되던 해 여름이었다.
00:00:06,그 집 나는 성남에서 주택설계 사무소로 운영하고 있었다.
00:00:10,"말이 사무소고 운영이지, 실상은 거실 한편에 파티션을 놓고 사물을 보는 꼬리였다."
00:00:16,근속하던 회사에서 호기롭게 나와 사무소를 개업했지만
00:00:19,수조는 잘해야 반년에 두 건 보통 그 마저도 들어오지 않았다.
```

| 열 | 형식 | 설명 |
|---|---|---|
| 시간 | `HH:MM:SS` | 해당 발화가 시작된 음성 파일 내 오프셋 |
| 인식된 텍스트 | 문자열 | Whisper 가 인식한 발화 내용 |

---

### 키워드 검색 출력 예시

```
"화성" 검색 결과: 총 2건
────────────────────────────────────────────────────────────
  파일: 20260528-143052.csv  (2026-05-28 14:30:52)
  시간: 00:00:00
  내용: 화성 기지 일지를 시작합니다

  파일: 20260528-180001.csv  (2026-05-28 18:00:01)
  시간: 00:00:03
  내용: 화성의 일몰은 여전히 아름답습니다
```

---

## 6. 전체 흐름 요약

```
[마이크]
   │  sd.InputStream(callback=_audio_callback) 으로 스트림 오픈
   ▼
[버퍼 누적]  _audio_data : list[np.ndarray]
   │  콜백마다 float32 프레임 append
   ▼
[포맷 변환]
   │  np.concatenate → 단일 배열 병합
   │  × 32767 → np.clip → astype(int16)
   ▼
[WAV 저장]  records/YYYYMMDD-HHMMSS.wav
   │  wave.open() 으로 16-bit PCM 44100 Hz 기록
   ▼
[STT 변환]  openai-whisper  base 모델
   │  model.transcribe(**WHISPER_OPTIONS)
   │  세그먼트 필터링: 빈 텍스트 / 무음 제거
   ▼
[CSV 저장]  records/YYYYMMDD-HHMMSS.csv
   │  열: 시간(HH:MM:SS), 인식된 텍스트
   ▼
[키워드 검색]  전체 CSV 순회 → keyword.lower() in text.lower()
```
