# -*- coding: utf-8 -*-
import re


def remove_size_patterns_from_brand(brand_name):
    """브랜드명에서 사이즈 범위 패턴 제거 (예: (90~120) 등)"""
    if not brand_name: return brand_name
    result = re.sub(r'\([^)]*[~-][^)]*\)', '', brand_name)
    result = re.sub(r'\*[^\*]*[~-][^\*]*\*', '', result)
    return re.sub(r'\s+', ' ', result).strip()


def remove_front_parentheses(product_name):
    """상품명 앞에 붙은 괄호 제거 (예: (아동용) 티셔츠 → 티셔츠)"""
    if not product_name: return product_name
    return re.sub(r'^\s*\([^)]*\)\s*', '', product_name).strip()


def remove_keywords(product_name, keyword_list):
    """
    제외 키워드 제거.
    개선: re.IGNORECASE 플래그 적용 → 영문 대소문자 구분 없이 제거
    예: keyword='SET' 등록 시 소문자화된 'set'도 정상 제거됨
    """
    if not product_name or not keyword_list:
        return product_name
    result = product_name
    for kw in keyword_list:
        if not kw:
            continue
        cleaned_kw = kw.strip()
        # 괄호/별표로 감싸진 키워드 패턴 제거 (대소문자 무관)
        pat = r'[\(\*]' + re.escape(cleaned_kw.strip('(* )')) + r'[\)\*]'
        result = re.sub(pat, '', result, flags=re.IGNORECASE)
        # 일반 키워드 직접 제거 (개선: IGNORECASE 추가)
        result = re.sub(re.escape(cleaned_kw), '', result, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', result).strip()


def apply_smart_synonyms(text, rules, target_scope):
    """동의어 규칙 적용"""
    if not text: return text
    n = text.lower()
    for rule in rules:
        if target_scope not in rule['scope']:
            continue
        if rule['exact']:
            pat = r'(?<![가-힣a-z0-9])' + re.escape(rule['syn']) + r'(?![가-힣a-z0-9])'
            n = re.sub(pat, rule['std'], n)
        else:
            n = n.replace(rule['syn'], rule['std'])
    return n


def normalize_name(name, keyword_list, synonym_rules, target_scope="product"):
    """
    상품명 정규화 파이프라인.
    순서: 소문자화 → 키워드 제거 → 동의어 변환 → 괄호 제거 → 공백 제거
    개선: remove_keywords가 이제 대소문자 무관 처리되므로 영문 키워드도 정상 동작
    """
    if not name: return ""
    n = str(name).lower()
    n = remove_keywords(n, keyword_list)
    n = apply_smart_synonyms(n, synonym_rules, target_scope)
    n = re.sub(r'\([^)]*\)|\*[^\*]*\*', '', n)
    return re.sub(r'\s+', '', n)
