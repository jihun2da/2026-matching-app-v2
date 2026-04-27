# -*- coding: utf-8 -*-
import pandas as pd
import re
from typing import List, Dict, Tuple

import logic_text as lt
import logic_option as lo
import logic_scoring as ls
from database import get_db, MasterProduct, Synonym, Keyword


class BrandMatchingSystem:

    def __init__(self):
        self.brand_data = None
        self.db_records = []
        self.synonym_rules = []
        self.keyword_list = []
        self.brand_index = {}
        self.product_index = {}
        self._match_cache = {}  # 개선: 매칭 결과 캐시 (동일 입력 재계산 방지)
        self.load_data()

    def load_data(self):
        """DB에서 전체 데이터 로드 및 인덱스 구축"""
        self._match_cache = {}  # 데이터 갱신 시 캐시 초기화
        with get_db() as db:
            # 동의어 로드
            syns = db.query(Synonym).filter(Synonym.is_active == True).all()
            self.synonym_rules = []
            for s in syns:
                scope = []
                if s.apply_brand: scope.append('brand')
                if s.apply_product: scope.append('product')
                if s.apply_option: scope.append('option')
                self.synonym_rules.append({
                    'std': s.standard_word.lower(),
                    'syn': s.synonym_word.lower(),
                    'scope': scope,
                    'exact': s.is_exact_match
                })

            # 키워드 로드
            self.keyword_list = [k.keyword_text for k in db.query(Keyword).all()]

            # 상품 데이터 로드 및 인덱스 구축
            prods = db.query(MasterProduct).all()
            data = []
            for p in prods:
                p_norm = lt.normalize_name(p.product_name, self.keyword_list, self.synonym_rules, 'product')
                raw_db_c, raw_db_s = lo.get_db_option_list(p.options)
                db_c_expanded = list(set(
                    raw_db_c + [lt.apply_smart_synonyms(c, self.synonym_rules, 'option') for c in raw_db_c]
                ))
                db_s_expanded = list(set(
                    raw_db_s + [lt.apply_smart_synonyms(s, self.synonym_rules, 'option') for s in raw_db_s]
                ))

                row = {
                    '브랜드': p.brand,
                    '상품명': p.product_name,
                    '옵션입력': p.options,
                    '중도매': p.wholesale_name,
                    '공급가': p.supply_price,
                    '_p_norm': p_norm,
                    '_db_colors': db_c_expanded,
                    '_db_sizes': db_s_expanded,
                    '_db_colors_raw': raw_db_c,
                    '_db_sizes_raw': raw_db_s
                }
                data.append(row)

                # 브랜드 인덱스
                b_norm = lt.apply_smart_synonyms(str(p.brand), self.synonym_rules, 'brand')
                b_key = "".join(re.sub(r'[\[\]\(\)]', '', str(b_norm)).lower().split())
                if b_key not in self.brand_index:
                    self.brand_index[b_key] = []
                self.brand_index[b_key].append(row)

                # 상품명 인덱스
                if p_norm not in self.product_index:
                    self.product_index[p_norm] = []
                self.product_index[p_norm].append(row)

            self.db_records = data
            self.brand_data = pd.DataFrame(data)

    def extract_third_word_from_address(self, address: str) -> str:
        """주소에서 3번째 단어 추출 (위탁자명 구분용)"""
        if not address or pd.isna(address):
            return ""
        words = str(address).strip().split()
        return words[2] if len(words) >= 3 else ""

    def convert_sheet1_to_sheet2(self, sheet1_df: pd.DataFrame) -> pd.DataFrame:
        """발주 원본 엑셀(Sheet1)을 매칭용 형식(Sheet2)으로 변환"""
        sheet2_columns = [
            'A열(ㅇ)', 'B열(미등록주문)', 'C열(주문일)', 'D열(아이디주문번호)', 'E열(ㅇ)',
            'F열(주문자명)', 'G열(위탁자명)', 'H열(브랜드)', 'I열(상품명)', 'J열(색상)',
            'K열(사이즈)', 'L열(수량)', 'M열(옵션가)', 'N열(중도매명)', 'O열(도매가격)',
            'P열(미송)', 'Q열(비고)', 'R열(이름)', 'S열(전화번호)', 'T열(주소)',
            'U열(아이디)', 'V열(배송메세지)', 'W열(금액)'
        ]
        if sheet1_df.empty:
            return pd.DataFrame(columns=sheet2_columns)

        sheet2_rows = []
        for i, (idx, row) in enumerate(sheet1_df.iterrows()):
            sheet2_row = {col: "" for col in sheet2_columns}

            if len(sheet1_df.columns) >= 1: sheet2_row['C열(주문일)'] = str(row.iloc[0])
            if len(sheet1_df.columns) >= 2: sheet2_row['D열(아이디주문번호)'] = str(row.iloc[1])
            if len(sheet1_df.columns) >= 3: sheet2_row['F열(주문자명)'] = str(row.iloc[2])
            if len(sheet1_df.columns) >= 4:
                name = str(row.iloc[3])
                addr = str(row.iloc[10]) if len(sheet1_df.columns) >= 11 else ""
                addr_3rd = self.extract_third_word_from_address(addr)
                sheet2_row['G열(위탁자명)'] = f"{name}({addr_3rd})" if addr_3rd else name

            if len(sheet1_df.columns) >= 5:
                raw_full = str(row.iloc[4]).strip()

                # 첫 번째 공백을 기준으로 브랜드명 / 상품명 분리
                parts = raw_full.split(' ', 1)
                if len(parts) == 2:
                    sheet2_row['H열(브랜드)'] = lt.remove_size_patterns_from_brand(parts[0])
                    sheet2_row['I열(상품명)'] = lt.remove_keywords(
                        lt.remove_front_parentheses(parts[1]), self.keyword_list
                    )
                else:
                    sheet2_row['H열(브랜드)'] = ""
                    sheet2_row['I열(상품명)'] = lt.remove_keywords(
                        lt.remove_front_parentheses(raw_full), self.keyword_list
                    )

            if len(sheet1_df.columns) >= 6:
                sheet2_row['J열(색상)'], sheet2_row['K열(사이즈)'] = lo.parse_options(str(row.iloc[5]))
            if len(sheet1_df.columns) >= 7:
                try:
                    sheet2_row['L열(수량)'] = int(row.iloc[6])
                except Exception:
                    sheet2_row['L열(수량)'] = 1
            if len(sheet1_df.columns) >= 8:
                sheet2_row['M열(옵션가)'] = str(row.iloc[7])
            if len(sheet1_df.columns) >= 9:
                name = str(row.iloc[8])
                addr = str(row.iloc[10]) if len(sheet1_df.columns) >= 11 else ""
                addr_3rd = self.extract_third_word_from_address(addr)
                sheet2_row['R열(이름)'] = f"{name}({addr_3rd})" if addr_3rd else name
            if len(sheet1_df.columns) >= 10: sheet2_row['S열(전화번호)'] = str(row.iloc[9])
            if len(sheet1_df.columns) >= 11: sheet2_row['T열(주소)'] = str(row.iloc[10])
            if len(sheet1_df.columns) >= 12: sheet2_row['V열(배송메세지)'] = str(row.iloc[11])

            sheet2_rows.append(sheet2_row)

        return pd.DataFrame(sheet2_rows, columns=sheet2_columns)

    def match_row(self, b: str, p: str, s: str, c: str, weights: dict) -> Tuple:
        """단일 행 매칭 처리"""
        if not p:
            return "매칭 실패", "", "", False, 0.0, []

        # ─────────────────────────────────────────────
        # 개선: 캐시 적용 - 동일 입력 재계산 방지
        # 반복 발주서(같은 상품명이 여러 번 등장)에서 성능 향상
        # ─────────────────────────────────────────────
        cache_key = f"{b}|{p}|{s}|{c}|{weights.get('p_threshold')}|{weights.get('p_w')}|{weights.get('o_w')}"
        if cache_key in self._match_cache:
            return self._match_cache[cache_key]

        p_threshold = weights.get('p_threshold', 80)
        p_w = weights.get('p_w', 0.5)
        o_w = weights.get('o_w', 50.0)

        b_norm = lt.apply_smart_synonyms(b, self.synonym_rules, 'brand')
        b_clean = "".join(re.sub(r'[\[\]\(\)]', '', b_norm).lower().split())
        p_norm = lt.normalize_name(p, self.keyword_list, self.synonym_rules, 'product')

        candidates = self.brand_index.get(b_clean, []) if b_clean else self.db_records

        up_c_norm = lt.apply_smart_synonyms(c, self.synonym_rules, 'option')
        up_s_norm = lt.apply_smart_synonyms(s, self.synonym_rules, 'option')

        best_m, best_s = None, 0.0
        all_scored = []  # 추천용 사전 계산 목록 (DB 재탐색 방지)

        for rd in candidates:
            row_p_norm = rd.get('_p_norm', '')
            p_sim = ls.get_sim(p_norm, row_p_norm)

            # 추천용 점수 기록 (브랜드 매칭 보너스 50점 포함)
            all_scored.append({
                'rd': rd,
                'p_sim': p_sim,
                'sort_score': p_sim + 50.0,
                'is_b_match': True
            })

            if p_sim >= p_threshold:
                db_colors = rd.get('_db_colors', [])
                db_sizes = rd.get('_db_sizes', [])
                c_ok = lo.check_option_inclusion(up_c_norm, db_colors)
                s_ok = lo.check_option_inclusion(up_s_norm, db_sizes)

                if c_ok and s_ok:
                    raw_score = (p_sim * p_w) + o_w
                    # ─────────────────────────────────────────────
                    # 개선: 점수 정규화 (0~100 범위)
                    # 기존: 가중치 설정에 따라 최대 200점까지 가능 → 기준 혼란
                    # 개선: 항상 0~100 범위로 정규화 → 90점=정확매칭이 항상 일관됨
                    # ─────────────────────────────────────────────
                    max_possible = (100 * p_w) + o_w
                    score = (raw_score / max_possible) * 100 if max_possible > 0 else 0.0

                    if score > best_s:
                        best_s, best_m = score, rd

        if best_m and best_s >= 60:
            result = (best_m.get('공급가', 0), best_m.get('중도매', ''), best_m, True, best_s, [])
            self._match_cache[cache_key] = result
            return result

        # 개선: 이미 계산한 all_scored 재활용 → 추천 생성 시 DB 재탐색 없음
        suggs = ls.get_4step_recommendations(
            p_norm, b_clean, self.db_records,
            up_c_norm, up_s_norm, c, s, p_threshold,
            pre_scored=all_scored if b_clean else None
        )

        result = ("매칭 실패", "", "", False, best_s, suggs)
        self._match_cache[cache_key] = result
        return result

    def process_matching(
        self,
        sheet2_df: pd.DataFrame,
        weights: dict,
        progress_callback=None
    ) -> Tuple[pd.DataFrame, List[Dict], List[Dict]]:
        """전체 발주서 매칭 처리"""
        total_rows = len(sheet2_df)
        success_products = []
        failed_products = []
        results_n, results_o, results_w, results_status = [], [], [], []

        for index, row in sheet2_df.iterrows():
            if progress_callback:
                progress_callback(index + 1, total_rows)

            b = str(row.get('H열(브랜드)', '')).strip()
            p = str(row.get('I열(상품명)', '')).strip()
            s = str(row.get('K열(사이즈)', '')).strip()
            c = str(row.get('J열(색상)', '')).strip()
            qty = row.get('L열(수량)', 1)

            price, wh, match_info, ok, score, suggs = self.match_row(b, p, s, c, weights)

            if ok and price != "매칭 실패":
                results_n.append(wh)
                results_o.append(price)
                results_status.append("정확매칭" if score >= 90 else "유사매칭")
                try:
                    results_w.append(float(price) * int(qty))
                except Exception:
                    results_w.append(0)
                success_products.append({
                    '[발주] 브랜드': b,
                    '[발주] 상품명': p,
                    '[발주] 옵션': f"{c} / {s}",
                    '▶ 매칭상태': "정확매칭" if score >= 90 else "유사매칭",
                    '▶ 매칭점수': f"{score:.1f}점",
                    '[DB] 브랜드': match_info.get('브랜드', ''),
                    '[DB] 상품명': match_info.get('상품명', ''),
                    '[DB] 옵션입력': match_info.get('옵션입력', '')
                })
            else:
                results_n.append("")
                results_o.append(0)
                results_w.append(0)
                results_status.append("매칭실패")
                failed_products.append({
                    '발주_브랜드': b,
                    '발주_상품명': p,
                    '옵션': f"{c}/{s}",
                    '💡추천_1순위': suggs[0] if len(suggs) > 0 else "추천 없음",
                    '💡추천_2순위': suggs[1] if len(suggs) > 1 else "추천 없음",
                    '💡추천_3순위': suggs[2] if len(suggs) > 2 else "추천 없음",
                    '💡추천_4순위': suggs[3] if len(suggs) > 3 else "추천 없음"
                })

        sheet2_df['N열(중도매명)'] = results_n
        sheet2_df['O열(도매가격)'] = results_o
        sheet2_df['W열(금액)'] = results_w
        sheet2_df['매칭_상태'] = results_status

        return sheet2_df, success_products, failed_products
