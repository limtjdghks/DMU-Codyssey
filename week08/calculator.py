import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QGridLayout, QPushButton, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase

# 시스템에서 사용 가능한 UI 폰트를 선택한다.
# Qt가 인식하지 못하는 폰트를 지정하면 경고가 발생하므로
# 설치된 폰트 목록을 확인한 뒤 우선순위대로 선택한다.
_FONT_CANDIDATES = ['Helvetica Neue', 'Helvetica', 'Arial', 'sans-serif']
_UI_FONT = 'Arial'   # QApplication 생성 전에는 families() 호출 불가 — 이후 초기화


def _resolve_font():
    """시스템에 설치된 폰트 중 우선순위가 가장 높은 것을 반환한다."""
    available = set(QFontDatabase.families())
    for candidate in _FONT_CANDIDATES:
        if candidate in available:
            return candidate
    return ''   # Qt 기본 폰트 사용

# ------------------------------------------------------------------ #
# 상수 정의                                                            #
# ------------------------------------------------------------------ #

# 색상 팔레트 (아이폰 계산기 기준)
COLOR_BG = '#1c1c1e'            # 앱 배경
COLOR_DISPLAY_BG = '#1c1c1e'   # 디스플레이 배경
COLOR_BTN_FUNC = '#505050'      # AC / +- / % 버튼 (기능키)
COLOR_BTN_OP = '#ff9f0a'        # 연산자 버튼 색 (÷ × − +  =)
COLOR_BTN_OP_ACTIVE = '#ffffff' # 연산자 선택됐을 때 버튼 배경
COLOR_BTN_NUM = '#333333'       # 숫자 버튼
COLOR_TEXT_DARK = '#000000'     # 기능키 텍스트
COLOR_TEXT_LIGHT = '#ffffff'    # 숫자·연산자 버튼 텍스트
COLOR_TEXT_OP_ACTIVE = '#ff9f0a'  # 선택된 연산자 텍스트

# 버튼 레이아웃 정의
# (표시 텍스트, 열 인덱스, 행 인덱스, 컬럼 span)
BUTTONS = [
    # row 0 — 기능키
    ('AC', 0, 0, 1),
    ('+/-', 1, 0, 1),
    ('%', 2, 0, 1),
    ('÷', 3, 0, 1),
    # row 1
    ('7', 0, 1, 1),
    ('8', 1, 1, 1),
    ('9', 2, 1, 1),
    ('×', 3, 1, 1),
    # row 2
    ('4', 0, 2, 1),
    ('5', 1, 2, 1),
    ('6', 2, 2, 1),
    ('−', 3, 2, 1),
    # row 3
    ('1', 0, 3, 1),
    ('2', 1, 3, 1),
    ('3', 2, 3, 1),
    ('+', 3, 3, 1),
    # row 4 — 0 버튼은 2칸 넓이
    ('0', 0, 4, 2),
    ('.', 2, 4, 1),
    ('=', 3, 4, 1),
]

# 연산자 집합
OPERATORS = {'÷', '×', '−', '+'}


def _btn_colors(label):
    """버튼 레이블에 따라 (배경색, 텍스트색) 튜플을 반환한다."""
    if label in ('AC', '+/-', '%'):
        return COLOR_BTN_FUNC, COLOR_TEXT_DARK
    if label in OPERATORS or label == '=':
        return COLOR_BTN_OP, COLOR_TEXT_LIGHT
    return COLOR_BTN_NUM, COLOR_TEXT_LIGHT


def _btn_style(bg, fg, radius=40, width=80, height=80):
    """QPushButton 용 CSS 스타일 문자열을 반환한다.

    border-radius 를 버튼 높이의 절반으로 고정하여 완전한 원형을 보장한다.
    Fusion 스타일이 크기를 재정의하지 못하도록 min/max 크기를 함께 지정한다.
    """
    return (
        f'QPushButton {{'
        f'  background-color: {bg};'
        f'  color: {fg};'
        f'  border-radius: {radius}px;'
        f'  border: none;'
        f'  min-width: {width}px;'
        f'  max-width: {width}px;'
        f'  min-height: {height}px;'
        f'  max-height: {height}px;'
        f'  padding: 0px;'
        f'}}'
        f'QPushButton:pressed {{'
        f'  background-color: rgba(255,255,255,0.25);'
        f'  border-radius: {radius}px;'
        f'}}'
    )


# ------------------------------------------------------------------ #
# 계산 엔진                                                            #
# ------------------------------------------------------------------ #

class CalculatorEngine:
    """계산기의 상태와 4칙 연산 로직을 담당하는 클래스.

    아이폰 계산기의 동작 방식을 따른다.
    - 연산자를 누르면 첫 번째 피연산자와 연산자를 저장한다.
    - 두 번째 숫자 입력 후 '=' 또는 다른 연산자를 누르면 계산한다.
    - '=' 을 연속으로 누르면 마지막 연산자와 피연산자를 재사용한다.
    """

    def __init__(self):
        self._reset_all()

    def _reset_all(self):
        """모든 상태를 초기화한다."""
        self._display = '0'     # 화면에 표시할 문자열
        self._operand1 = None   # 첫 번째 피연산자
        self._operator = None   # 현재 연산자
        self._operand2 = None   # 마지막 피연산자 (= 연속 입력 재사용)
        self._wait_operand = False  # True: 다음 입력이 새 숫자 시작
        self._just_equaled = False  # True: 방금 = 을 눌렀음

    def _set_error(self):
        """오류 상태로 전환한다. 디스플레이를 'Error' 로 설정한 뒤
        내부 상태를 초기화하되 디스플레이 값은 유지한다.
        """
        self._reset_all()
        self._display = 'Error'

    @property
    def display(self):
        return self._display

    def _format(self, value):
        """숫자를 화면에 표시할 문자열로 변환한다.

        정수이면 소수점을 제거하고, 소수이면 불필요한 0 을 제거한다.
        결과가 너무 길면 지수 표기법으로 표시한다.
        """
        if value != value:          # NaN 체크
            return 'Error'
        try:
            if value == int(value) and abs(value) < 1e15:
                text = str(int(value))
            else:
                text = f'{value:.10g}'
        except (OverflowError, ValueError):
            text = 'Error'
        return text

    def _apply_operator(self, a, op, b):
        """두 피연산자와 연산자로 계산을 수행하고 결과를 반환한다."""
        if op == '+':
            return a + b
        if op == '−':
            return a - b
        if op == '×':
            return a * b
        if op == '÷':
            if b == 0:
                return None     # 0 나누기 예외 → None 으로 처리
            return a / b
        return a

    def press_digit(self, digit):
        """숫자(0-9) 또는 소수점 입력을 처리한다."""
        # = 직후 숫자 입력 → 새 계산 시작
        if self._just_equaled:
            self._operand1 = None
            self._operator = None
            self._just_equaled = False
            self._wait_operand = False

        if self._wait_operand:
            # 연산자 입력 직후 → 새 피연산자 입력 시작
            self._display = '0' if digit != '.' else '0.'
            self._wait_operand = False

        # 소수점 중복 방지
        if digit == '.' and '.' in self._display:
            return
        # 정수 자릿수 제한 (최대 9자리)
        if digit != '.' and self._display == '0':
            self._display = digit
        elif digit != '.' and len(self._display.replace('-', '').replace('.', '')) >= 9:
            return
        else:
            self._display += digit

    def press_operator(self, op):
        """연산자(+ − × ÷) 입력을 처리한다."""
        self._just_equaled = False
        current = float(self._display)

        if self._operator and not self._wait_operand:
            # 이미 연산자가 있고 두 번째 숫자가 입력된 상태 → 중간 계산
            result = self._apply_operator(self._operand1, self._operator, current)
            if result is None:
                self._set_error()
                return
            self._operand1 = result
            self._display = self._format(result)
        else:
            self._operand1 = current

        self._operator = op
        self._wait_operand = True

    def press_equal(self):
        """= 키 입력을 처리한다."""
        if self._operator is None:
            return

        current = float(self._display)

        if self._just_equaled:
            # = 연속 입력: 마지막 피연산자를 재사용
            operand2 = self._operand2
        else:
            operand2 = current
            self._operand2 = operand2

        result = self._apply_operator(self._operand1, self._operator, operand2)
        if result is None:
            self._set_error()
            return

        self._display = self._format(result)
        self._operand1 = result
        self._wait_operand = False
        self._just_equaled = True

    def press_clear(self):
        """AC(모두 지우기) 키 입력을 처리한다."""
        self._reset_all()

    def press_sign(self):
        """+/- 키 입력: 현재 숫자의 부호를 반전한다."""
        try:
            value = float(self._display)
            value = -value
            self._display = self._format(value)
        except ValueError:
            pass

    def press_percent(self):
        """% 키 입력: 현재 숫자를 백분율(÷100)로 변환한다."""
        try:
            value = float(self._display)
            value = value / 100
            self._display = self._format(value)
        except ValueError:
            pass


# ------------------------------------------------------------------ #
# UI                                                                   #
# ------------------------------------------------------------------ #

class Calculator(QWidget):
    """아이폰 계산기와 유사한 레이아웃의 계산기 위젯."""

    def __init__(self):
        super().__init__()
        self._engine = CalculatorEngine()
        self._active_op_btn = None   # 현재 강조 표시된 연산자 버튼
        self._op_buttons = {}        # 연산자 버튼 참조 dict
        self._init_ui()

    def _init_ui(self):
        """UI 전체를 초기화한다."""
        # QApplication 생성 이후에만 폰트 목록 조회가 가능하므로 여기서 결정
        global _UI_FONT
        _UI_FONT = _resolve_font()

        self.setWindowTitle('Calculator')
        self.setFixedSize(380, 580)
        self.setStyleSheet(f'background-color: {COLOR_BG};')

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 40, 12, 12)
        outer.setSpacing(0)

        # 디스플레이
        self._display_label = QLabel('0')
        self._display_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self._display_label.setStyleSheet(
            f'color: white; background-color: {COLOR_DISPLAY_BG};'
            f'padding: 0 12px 8px 12px;'
        )
        self._display_label.setFont(QFont(_UI_FONT, 64, QFont.Weight.Light))
        self._display_label.setMinimumHeight(120)
        self._display_label.setMaximumHeight(140)
        self._display_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        outer.addWidget(self._display_label)

        # 버튼 그리드
        grid = QGridLayout()
        grid.setSpacing(10)
        outer.addLayout(grid)

        btn_size = 80
        # 정원(正圓)을 만들려면 border-radius = 높이 / 2
        btn_radius = btn_size // 2
        # '0' 버튼: 두 칸 너비 + 간격(10px)
        zero_w = btn_size * 2 + 10

        for label, col, row, span in BUTTONS:
            btn = QPushButton(label)
            bg, fg = _btn_colors(label)
            btn.setFont(QFont(_UI_FONT, 24, QFont.Weight.Normal))

            if span == 2:
                # '0' 버튼: 가로로 길쭉한 알약(pill) 형태, 좌측 정렬 텍스트
                # border-radius = 높이/2 로 양 끝만 반원을 만든다
                btn.setFixedSize(zero_w, btn_size)
                btn.setStyleSheet(
                    _btn_style(bg, fg,
                               radius=btn_radius,
                               width=zero_w,
                               height=btn_size)
                    + f'QPushButton {{'
                    f'  text-align: left;'
                    f'  padding-left: 28px;'
                    f'}}'
                    + f'QPushButton:pressed {{'
                    f'  background-color: rgba(255,255,255,0.25);'
                    f'  text-align: left;'
                    f'  padding-left: 28px;'
                    f'}}'
                )
            else:
                # 나머지 버튼: 정사각형 → border-radius = 절반 → 완전한 원
                btn.setFixedSize(btn_size, btn_size)
                btn.setStyleSheet(
                    _btn_style(bg, fg,
                               radius=btn_radius,
                               width=btn_size,
                               height=btn_size)
                )

            btn.clicked.connect(self._make_handler(label))
            grid.addWidget(btn, row, col, 1, span)

            if label in OPERATORS or label == '=':
                self._op_buttons[label] = btn

        self._update_display()

    def _make_handler(self, label):
        """버튼 레이블에 대응하는 클릭 핸들러 클로저를 반환한다."""
        def handler():
            self._on_button_click(label)
        return handler

    def _on_button_click(self, label):
        """버튼 클릭 이벤트를 처리한다."""
        if label == 'AC':
            self._engine.press_clear()
            self._clear_op_highlight()

        elif label == '+/-':
            self._engine.press_sign()

        elif label == '%':
            self._engine.press_percent()

        elif label in OPERATORS:
            self._engine.press_operator(label)
            self._highlight_op(label)

        elif label == '=':
            self._engine.press_equal()
            self._clear_op_highlight()

        else:
            # 숫자 또는 소수점
            self._engine.press_digit(label)
            self._clear_op_highlight()

        self._update_display()

    def _update_display(self):
        """엔진의 현재 표시값을 레이블에 반영한다.

        숫자 길이에 따라 폰트 크기를 자동 조절한다.
        """
        text = self._engine.display
        length = len(text.replace('-', '').replace('.', ''))

        if length <= 6:
            font_size = 64
        elif length <= 8:
            font_size = 52
        else:
            font_size = 40

        self._display_label.setFont(
            QFont(_UI_FONT, font_size, QFont.Weight.Light)
        )
        self._display_label.setText(text)

    def _highlight_op(self, op):
        """선택된 연산자 버튼을 반전(흰 배경 + 주황 텍스트) 으로 강조한다."""
        self._clear_op_highlight()
        btn = self._op_buttons.get(op)
        if btn:
            btn.setStyleSheet(
                _btn_style(COLOR_BTN_OP_ACTIVE, COLOR_TEXT_OP_ACTIVE,
                           radius=40, width=80, height=80)
            )
            self._active_op_btn = btn

    def _clear_op_highlight(self):
        """이전에 강조된 연산자 버튼의 스타일을 원래대로 복원한다."""
        if self._active_op_btn:
            self._active_op_btn.setStyleSheet(
                _btn_style(COLOR_BTN_OP, COLOR_TEXT_LIGHT,
                           radius=40, width=80, height=80)
            )
            self._active_op_btn = None


# ------------------------------------------------------------------ #
# 진입점                                                               #
# ------------------------------------------------------------------ #

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Calculator()
    window.show()
    sys.exit(app.exec())
