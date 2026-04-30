import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QGridLayout, QPushButton, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase

# ------------------------------------------------------------------ #
# 폰트                                                                 #
# ------------------------------------------------------------------ #

_FONT_CANDIDATES = ['Helvetica Neue', 'Helvetica', 'Arial']
_UI_FONT = 'Arial'


def _resolve_font():
    """시스템에 설치된 폰트 중 우선순위가 높은 것을 반환한다."""
    available = set(QFontDatabase.families())
    for candidate in _FONT_CANDIDATES:
        if candidate in available:
            return candidate
    return ''


# ------------------------------------------------------------------ #
# 색상 / 레이아웃 상수                                                  #
# ------------------------------------------------------------------ #

COLOR_BG = '#1c1c1e'
COLOR_DISPLAY_BG = '#1c1c1e'
COLOR_BTN_FUNC = '#505050'
COLOR_BTN_OP = '#ff9f0a'
COLOR_BTN_OP_ACTIVE = '#ffffff'
COLOR_BTN_NUM = '#333333'
COLOR_TEXT_DARK = '#000000'
COLOR_TEXT_LIGHT = '#ffffff'
COLOR_TEXT_OP_ACTIVE = '#ff9f0a'

# (레이블, 열, 행, colspan)
BUTTONS = [
    ('AC',  0, 0, 1), ('+/-', 1, 0, 1), ('%',  2, 0, 1), ('÷', 3, 0, 1),
    ('7',   0, 1, 1), ('8',   1, 1, 1), ('9',  2, 1, 1), ('×', 3, 1, 1),
    ('4',   0, 2, 1), ('5',   1, 2, 1), ('6',  2, 2, 1), ('−', 3, 2, 1),
    ('1',   0, 3, 1), ('2',   1, 3, 1), ('3',  2, 3, 1), ('+', 3, 3, 1),
    ('0',   0, 4, 2), ('.',   2, 4, 1), ('=',  3, 4, 1),
]

OPERATORS = {'÷', '×', '−', '+'}

# 처리 가능한 숫자 범위 (이 이상이면 오버플로 처리)
MAX_VALUE = 1e99
# 표시 소수점 자리 수
DISPLAY_DECIMAL = 6
# 숫자 버튼 최대 입력 자릿수
MAX_DIGITS = 9


# ------------------------------------------------------------------ #
# 계산 엔진 — Calculator 클래스                                         #
# ------------------------------------------------------------------ #

class Calculator:
    """사칙 연산 및 보조 기능을 담당하는 계산기 핵심 클래스.

    상태 머신으로 동작하며 아이폰 계산기와 동일한 입력 흐름을 따른다.

    주요 메소드
    ----------
    add / subtract / multiply / divide : 연산자 설정
    equal         : 결과 계산 및 표시
    reset         : 전체 초기화
    negative_positive : 부호 반전
    percent       : 퍼센트(÷100) 변환
    input_digit   : 숫자 및 소수점 입력
    """

    def __init__(self):
        self._reset_state()

    # ---- 내부 상태 관리 -------------------------------------------- #

    def _reset_state(self):
        """모든 내부 상태를 초기값으로 설정한다."""
        self._display = '0'       # 현재 화면 문자열
        self._operand = None      # 첫 번째 피연산자
        self._operator = None     # 저장된 연산 함수 (callable)
        self._op_label = ''       # 연산자 레이블 (UI 강조용)
        self._new_input = False   # True: 다음 입력부터 새 숫자 시작
        self._just_equal = False  # True: 바로 직전에 = 를 눌렀음
        self._last_operand = None # = 연속 입력 시 재사용할 피연산자

    def _set_error(self, msg='Error'):
        """오류 상태로 전환한다."""
        self._reset_state()
        self._display = msg

    def _format(self, value):
        """float 를 화면에 출력할 문자열로 변환한다.

        - 정수이면 소수점 제거
        - 소수점 이하가 DISPLAY_DECIMAL(6)자리 초과이면 반올림
        - 처리 범위(MAX_VALUE)를 넘으면 'Error' 반환
        """
        try:
            if abs(value) > MAX_VALUE:
                return 'Error'
            # 정수 판별
            if value == int(value) and abs(value) < 1e15:
                return str(int(value))
            # 소수점 6자리로 반올림 후 불필요한 0 제거
            rounded = round(value, DISPLAY_DECIMAL)
            text = f'{rounded:.{DISPLAY_DECIMAL}f}'.rstrip('0').rstrip('.')
            # 반올림 후에도 정수가 됐으면 소수점 제거
            if '.' not in text:
                return text
            return text
        except (OverflowError, ValueError):
            return 'Error'

    def _apply_pending(self):
        """저장된 연산자가 있고, 새 숫자가 입력된 상태라면 중간 계산을 수행한다.

        3 + 5 × 를 입력할 때 3+5=8 을 먼저 계산하는 체이닝 동작이다.
        """
        if self._operator is None or self._new_input:
            return
        try:
            current = float(self._display)
            result = self._operator(self._operand, current)
            formatted = self._format(result)
            if formatted == 'Error':
                self._set_error()
                return
            self._operand = result
            self._display = formatted
        except (ZeroDivisionError, OverflowError, ValueError):
            self._set_error()

    def _store_operator(self, op_func, op_label):
        """현재 표시 값을 첫 번째 피연산자로 저장하고 연산자를 설정한다."""
        if self._display == 'Error':
            return
        self._apply_pending()
        if self._display == 'Error':
            return
        try:
            self._operand = float(self._display)
        except ValueError:
            self._set_error()
            return
        self._operator = op_func
        self._op_label = op_label
        self._new_input = True
        self._just_equal = False

    # ---- 공개 메소드 (UI 에서 직접 호출) ----------------------------- #

    @property
    def display(self):
        """현재 화면에 표시할 문자열을 반환한다."""
        return self._display

    @property
    def active_operator(self):
        """현재 선택된 연산자 레이블을 반환한다 (UI 강조용)."""
        return self._op_label if self._new_input else ''

    def input_digit(self, digit):
        """숫자(0~9) 또는 소수점(.) 입력을 처리한다.

        - 연산자 입력 직후이면 새 숫자 입력 시작
        - = 직후이면 새 계산 시작
        - 소수점 중복 입력은 무시
        - 최대 MAX_DIGITS(9) 자리까지 입력 가능
        """
        if self._display == 'Error':
            self._reset_state()

        # = 직후 숫자 입력 → 완전히 새로운 계산
        if self._just_equal:
            self._operand = None
            self._operator = None
            self._op_label = ''
            self._just_equal = False
            self._new_input = False
            self._display = '0'

        # 연산자 직후 → 새 피연산자 입력 시작
        if self._new_input:
            self._display = '0'
            self._new_input = False

        # 소수점 중복 방지
        if digit == '.' and '.' in self._display:
            return

        # 자릿수 제한 (부호·소수점 제외 순수 숫자)
        digit_count = len(
            self._display.replace('-', '').replace('.', '')
        )
        if digit != '.' and digit_count >= MAX_DIGITS:
            return

        if digit != '.' and self._display in ('0', '-0'):
            self._display = '-' + digit if self._display == '-0' else digit
        else:
            self._display += digit

    def add(self):
        """덧셈 연산자를 설정한다."""
        self._store_operator(lambda a, b: a + b, '+')

    def subtract(self):
        """뺄셈 연산자를 설정한다."""
        self._store_operator(lambda a, b: a - b, '−')

    def multiply(self):
        """곱셈 연산자를 설정한다."""
        self._store_operator(lambda a, b: a * b, '×')

    def divide(self):
        """나눗셈 연산자를 설정한다.

        두 번째 피연산자가 0이면 오류를 발생시킨다.
        """
        def safe_divide(a, b):
            if b == 0:
                raise ZeroDivisionError('division by zero')
            return a / b
        self._store_operator(safe_divide, '÷')

    def equal(self):
        """현재 연산자와 피연산자로 결과를 계산하고 화면에 표시한다.

        연산자가 없으면 아무 동작도 하지 않는다.
        = 를 연속으로 누르면 마지막 연산자·피연산자를 재사용한다.
        """
        if self._operator is None:
            return
        if self._display == 'Error':
            return

        try:
            current = float(self._display)
        except ValueError:
            self._set_error()
            return

        # = 연속 입력: 직전 피연산자 재사용
        if self._just_equal:
            operand2 = self._last_operand
        else:
            operand2 = current
            self._last_operand = operand2

        try:
            result = self._operator(self._operand, operand2)
        except ZeroDivisionError:
            self._set_error('0으로 나눌 수 없습니다')
            return
        except OverflowError:
            self._set_error('범위 초과')
            return
        except Exception:
            self._set_error()
            return

        formatted = self._format(result)
        if formatted == 'Error':
            self._set_error('범위 초과')
            return

        self._display = formatted
        self._operand = result
        self._new_input = False
        self._just_equal = True
        self._op_label = ''

    def reset(self):
        """모든 상태를 초기화하고 화면을 0으로 설정한다."""
        self._reset_state()

    def negative_positive(self):
        """현재 표시 값의 양수/음수 부호를 반전한다."""
        if self._display in ('0', 'Error'):
            return
        try:
            value = float(self._display)
            value = -value
            self._display = self._format(value)
        except ValueError:
            pass

    def percent(self):
        """현재 표시 값을 백분율(÷100)로 변환한다."""
        if self._display == 'Error':
            return
        try:
            value = float(self._display)
            value = value / 100
            self._display = self._format(value)
        except (ValueError, OverflowError):
            self._set_error()


# ------------------------------------------------------------------ #
# UI 헬퍼                                                              #
# ------------------------------------------------------------------ #

def _btn_colors(label):
    """버튼 레이블에 따른 (배경색, 텍스트색) 반환한다."""
    if label in ('AC', '+/-', '%'):
        return COLOR_BTN_FUNC, COLOR_TEXT_DARK
    if label in OPERATORS or label == '=':
        return COLOR_BTN_OP, COLOR_TEXT_LIGHT
    return COLOR_BTN_NUM, COLOR_TEXT_LIGHT


def _btn_style(bg, fg, radius=40, width=80, height=80):
    """QPushButton CSS 스타일 문자열을 반환한다.

    border-radius = height // 2 로 설정해야 완전한 원형 버튼이 된다.
    min/max 크기를 명시해 Fusion 스타일의 재정의를 방지한다.
    """
    return (
        f'QPushButton {{'
        f'  background-color: {bg};'
        f'  color: {fg};'
        f'  border-radius: {radius}px;'
        f'  border: none;'
        f'  min-width: {width}px; max-width: {width}px;'
        f'  min-height: {height}px; max-height: {height}px;'
        f'  padding: 0px;'
        f'}}'
        f'QPushButton:pressed {{'
        f'  background-color: rgba(255,255,255,0.25);'
        f'  border-radius: {radius}px;'
        f'}}'
    )


# ------------------------------------------------------------------ #
# UI 위젯                                                              #
# ------------------------------------------------------------------ #

class CalculatorWindow(QWidget):
    """아이폰 계산기와 유사한 UI 를 제공하는 PyQt6 위젯.

    Calculator 클래스를 내부에 보유하고 버튼 클릭 이벤트를
    각 메소드 호출로 연결한다.
    """

    def __init__(self):
        super().__init__()
        self._calc = Calculator()
        self._op_buttons = {}       # 연산자 버튼 참조 (강조 처리용)
        self._active_op_btn = None  # 현재 강조된 연산자 버튼
        self._init_ui()

    def _init_ui(self):
        """위젯 전체 레이아웃과 버튼을 초기화한다."""
        global _UI_FONT
        _UI_FONT = _resolve_font()

        self.setWindowTitle('Calculator')
        self.setFixedSize(380, 580)
        self.setStyleSheet(f'background-color: {COLOR_BG};')

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 40, 12, 12)
        outer.setSpacing(0)

        # 디스플레이 레이블
        self._display_label = QLabel('0')
        self._display_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )
        self._display_label.setStyleSheet(
            f'color: white;'
            f'background-color: {COLOR_DISPLAY_BG};'
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
        btn_radius = btn_size // 2
        zero_w = btn_size * 2 + 10

        for label, col, row, span in BUTTONS:
            btn = QPushButton(label)
            bg, fg = _btn_colors(label)
            btn.setFont(QFont(_UI_FONT, 24, QFont.Weight.Normal))

            if span == 2:
                btn.setFixedSize(zero_w, btn_size)
                btn.setStyleSheet(
                    _btn_style(bg, fg,
                               radius=btn_radius,
                               width=zero_w,
                               height=btn_size)
                    + 'QPushButton { text-align: left; padding-left: 28px; }'
                    + 'QPushButton:pressed {'
                    '  background-color: rgba(255,255,255,0.25);'
                    '  text-align: left; padding-left: 28px; }'
                )
            else:
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

        self._refresh()

    # ---- 버튼 이벤트 연결 ------------------------------------------ #

    def _make_handler(self, label):
        """버튼 레이블에 대응하는 클릭 핸들러 클로저를 반환한다."""
        def handler():
            self._on_click(label)
        return handler

    def _on_click(self, label):
        """버튼 클릭을 Calculator 메소드 호출로 변환한다."""
        if label == 'AC':
            self._calc.reset()
            self._clear_op_highlight()

        elif label == '+/-':
            self._calc.negative_positive()

        elif label == '%':
            self._calc.percent()

        elif label == '+':
            self._calc.add()
            self._highlight_op(label)

        elif label == '−':
            self._calc.subtract()
            self._highlight_op(label)

        elif label == '×':
            self._calc.multiply()
            self._highlight_op(label)

        elif label == '÷':
            self._calc.divide()
            self._highlight_op(label)

        elif label == '=':
            self._calc.equal()
            self._clear_op_highlight()

        else:
            # 숫자 또는 소수점
            self._calc.input_digit(label)
            self._clear_op_highlight()

        self._refresh()

    # ---- 화면 갱신 ------------------------------------------------- #

    def _refresh(self):
        """Calculator 의 현재 display 값을 레이블에 반영한다.

        [보너스] 텍스트 길이에 따라 폰트 크기를 자동 조절해
        전체 내용이 잘리지 않고 한 번에 표시되도록 한다.
        """
        text = self._calc.display
        length = len(text)

        if length <= 6:
            font_size = 64
        elif length <= 9:
            font_size = 52
        elif length <= 13:
            font_size = 40
        else:
            font_size = 28

        self._display_label.setFont(
            QFont(_UI_FONT, font_size, QFont.Weight.Light)
        )
        self._display_label.setText(text)

    # ---- 연산자 버튼 강조 ------------------------------------------ #

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
    window = CalculatorWindow()
    window.show()
    sys.exit(app.exec())
