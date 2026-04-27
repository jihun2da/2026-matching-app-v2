# -*- coding: utf-8 -*-
import re
import logic_option as lo

# ─────────────────────────────────────────────
# 개선: rapidfuzz 우선 사용 (difflib 대비 10~30배 빠름)
# rapidfuzz 미설치 시 difflib로 자동 fallback
# ─────────────────────────────────────────────
try:
    from rapidfuzz import fuzz as _fuzz

    def get_sim(a, b):
        """유사도 계산 (rapidfuzz 버전 - 고속)"""
        if not a or not b:
            return 0.0
        a = re.sub(r'\s+', '', str(a).lower())
        b = re.sub(r'\s+', '', str(b).lower())
        return _fuzz.ratio(a, b)

except ImportError:
    from difflib import SequenceMatcher

    def get_sim(a, b):
        """유사도 계산 (difflib 버전 - rapidfuzz 미설치 시 fallback)"""
        if not a or not b:
            return 0.0
        a = re.sub(r'\s+', '', str(a).lower())
        b = re.sub(r'\s+', '', str(b).lower())
        return SequenceMatcher(None, a, b).ratio() * 100


def get_4step_recommendations(
    target_prod_norm, b_clean, db_records,
    up_c_norm, up_s_norm, raw_c, raw_s,
    p_threshold=80, pre_scored=None
):
    """
    매칭 실패 시 유사 상품 추천 목록 생성.

    개선: pre_scored 파라미터 추가
    - pre_scored가 전달되면 이미 계산된 점수를 재활용
    - 전체 DB 재탐색을 방지하여 성능 향상
    - 브랜드가 지정된 경우 효과 극대화
    """
    suggestions = []
    temp_list = []

    if pre_scored is not None:
        # 이미 계산된 점수 목록 재활용 (DB 재탐색 없음)
        source = pre_scored
    else:
        # pre_scored 없을 때 기존 방식으로 전체 탐색
        source = []
        for rd in db_records:
            db_b_clean = "".join(
                re.sub(r'[\[\]\(\)]', '', str(rd.get('브랜드', '')).lower()).split()
            )
            db_p_norm = rd.get('_p_norm', '')
            is_b_match = (b_clean == db_b_clean) if b_clean else True
            p_sim = get_sim(target_prod_norm, db_p_norm)
            if is_b_match or p_sim > 50:
                sort_score = p_sim + (50.0 if is_b_match else 0.0)
                source.append({
                    'rd': rd,
                    'p_sim': p_sim,
                    'sort_score': sort_score,
                    'is_b_match': is_b_match
                })

    for item in source:
        rd = item['rd']
        is_b_match = item.get('is_b_match', True)
        p_sim = item.get('p_sim', 0.0)

        reason = []
        if b_clean and not is_b_match:
            reason.append("브랜드 불일치")
        if p_sim < p_threshold:
            reason.append(f"상품명 유사도 낮음({p_sim:.0f}%)")

        db_colors = rd.get('_db_colors', [])
        db_sizes = rd.get('_db_sizes', [])
        if up_c_norm and not lo.check_option_inclusion(up_c_norm, db_colors):
            raw_db_colors = rd.get('_db_colors_raw', [])
            reason.append(f"색상 불포함(발주:{raw_c}/DB:{'|'.join(raw_db_colors)})")
        if up_s_norm and not lo.check_option_inclusion(up_s_norm, db_sizes):
            raw_db_sizes = rd.get('_db_sizes_raw', [])
            reason.append(f"사이즈 불포함(발주:{raw_s}/DB:{'|'.join(raw_db_sizes)})")

        fail_msg = " / ".join(reason) if reason else "옵션/브랜드 파싱 오류 또는 총점 미달"
        temp_list.append({
            'rd': rd,
            'sort_score': item.get('sort_score', 0.0),
            'reason': fail_msg
        })

    temp_list.sort(key=lambda x: x['sort_score'], reverse=True)

    for item in temp_list[:4]:
        try:
            price = f"{int(float(item['rd'].get('공급가', 0))):,}원"
        except Exception:
            price = f"{item['rd'].get('공급가', 0)}원"
        suggestions.append(
            f"[{item['rd'].get('브랜드', '')}] {item['rd'].get('상품명', '')} | {price} (사유: {item['reason']})"
        )

    return suggestions
