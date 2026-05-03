# -*- coding: utf-8 -*-
import re


# 빈값으로 취급할 문자열 목록
_EMPTY_VALUES = {'nan', 'none', 'n/a', 'na', '-', '--', '없음', '미입력', ''}


def _is_empty(val) -> bool:
    """빈값 여부 확인 (nan, None, 없음, N/A 등 다양한 표기 포함)"""
    if val is None:
        return True
    return str(val).strip().lower() in _EMPTY_VALUES


def normalize_for_comparison(val):
    """비교를 위해 괄호 앞부분 추출, 공백 제거, 소문자화, ~(물결)을 -(하이픈)으로 통일"""
    if not val: return ""
    v = str(val).split('(')[0].split('\uff08')[0].strip()  # 반각·전각 괄호 모두 제거
    v = v.lower().replace(" ", "")
    v = v.replace("~", "-")
    return v


def _clean_option_val(val: str) -> str:
    """옵션값 전처리: 반각·전각 괄호 앞부분만 추출, ~를 -로 통일"""
    return val.split('(')[0].split('\uff08')[0].strip().replace('~', '-')


def parse_options(option_text):
    """발주서 옵션 텍스트에서 색상/사이즈 분리"""
    if _is_empty(option_text):
        return "", ""
    text = str(option_text).strip()
    color, size = "", ""
    # 색상/컬러/Color/Colour 라벨 지원 (한글·영문·대소문자 혼용 모두 처리)
    c_m = re.search(r'(?:색상|컬러|Colou?r)\s*[=:]\s*([^,/;]+)', text, re.IGNORECASE)
    # 사이즈/Size 라벨 지원
    s_m = re.search(r'(?:사이즈|Size)\s*[=:]\s*([^,/;]+)', text, re.IGNORECASE)
    if c_m: color = _clean_option_val(c_m.group(1).strip())
    if s_m: size = _clean_option_val(s_m.group(1).strip())
    if not color and not size:
        parts = re.split(r'[/|;|-]', text)
        if len(parts) >= 2:
            color, size = _clean_option_val(parts[0].strip()), _clean_option_val(parts[1].strip())
        else:
            color = _clean_option_val(text)
    return color, size


def get_db_option_list(db_options_raw):
    """DB의 옵션(예: 색상{아이|퍼플}//사이즈{90|100})을 파싱하여 리스트로 반환"""
    if not db_options_raw:
        return [], []
    colors, sizes = [], []
    parts = str(db_options_raw).split("//")
    for part in parts:
        if "색상{" in part:
            match = re.search(r"색상\{([^}]*)\}", part)
            if match:
                colors = [c.strip() for c in match.group(1).split("|") if c.strip()]
        elif "사이즈{" in part:
            match = re.search(r"사이즈\{([^}]*)\}", part)
            if match:
                sizes = [s.strip() for s in match.group(1).split("|") if s.strip()]
    return colors, sizes


def check_option_inclusion(input_val, db_list):
    """
    발주서 옵션이 DB 옵션 리스트 중 하나와 일치하는지 검사.

    개선 전: 단순 in 연산 → "90" in "190" = True (오탐 발생)
    개선 후:
      1단계 - 정확 일치 우선 확인
      2단계 - 3자 이상일 때만 부분 포함 허용 (짧은 숫자 오탐 방지)
    """
    if not input_val:
        return True
    if not db_list:
        return False

    target = normalize_for_comparison(input_val)

    # 1단계: 정확 일치 확인 (가장 신뢰도 높음)
    for item in db_list:
        if normalize_for_comparison(item) == target:
            return True

    # 2단계: 부분 포함 확인 (단, 3자 이상인 경우에만 허용)
    # 예: "빨간" in "빨간색" → OK (3자)
    # 예: "90" in "190" → NG (2자, 2단계에서 걸러짐)
    for item in db_list:
        db_item = normalize_for_comparison(item)
        if len(target) >= 3 and target in db_item:
            return True
        if len(db_item) >= 3 and db_item in target:
            return True

    return False


def check_size_match(up_size, db_pattern):
    _, db_sizes = get_db_option_list(db_pattern)
    return 100.0 if check_option_inclusion(up_size, db_sizes) else 0.0


def extract_db_color(text):
    c, _ = get_db_option_list(text)
    return " ".join(c)


def extract_db_size(text):
    _, s = get_db_option_list(text)
    return " ".join(s)
