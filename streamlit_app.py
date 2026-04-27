# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime

from brand_matching_system import BrandMatchingSystem
from database import get_db, init_db, Synonym, Keyword, MasterProduct
from sqlalchemy import or_, func, cast
from sqlalchemy import Date as SADate

# ─────────────────────────────────────────────
# 개선: 앱 시작 시 명시적으로 DB 테이블 초기화
# (import 시 자동 실행되던 방식 → 명시적 호출로 변경)
# ─────────────────────────────────────────────
init_db()

st.set_page_config(
    page_title="2026 브랜드 매칭 시스템 v2",
    layout="wide",
    initial_sidebar_state="expanded"
)

if 'match_state' not in st.session_state:
    st.session_state.match_state = {
        'completed': False, 'final_df': None,
        'success_products': [], 'failed_products': [],
        'total_count': 0, 'success_count': 0, 'fail_count': 0
    }

# ─────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ 시스템 설정")
    st.caption("🚀 v2 — 성능 및 매칭 로직 개선 버전")
    st.markdown("### ⚖️ 매칭 가중치 및 커트라인 조절")
    p_threshold = st.slider("상품명 유사도 통과 커트라인 (%)", 50, 100, 80, 5,
                            help="이 점수 이상이어야 매칭을 시도합니다 (기본 80%)")
    p_w = st.slider("상품명 유사도 가중치", 0.1, 1.0, 0.5, 0.1,
                    help="상품명이 비슷할 때 주는 기본 점수 비율")
    o_w = st.slider("옵션 일치 보너스", 0, 100, 50, 5,
                    help="색상/사이즈가 모두 일치하면 주는 가산점")

    weights = {'p_w': p_w, 'o_w': o_w, 'p_threshold': p_threshold}

    st.markdown("---")
    menu = st.radio("작업 메뉴를 선택하세요", ["✅ 발주서 자동 매칭", "📚 동의어/키워드 관리", "📊 DB 연동 상태"])
    st.markdown("---")
    st.info("💡 Tip: 화면을 이동해도 작업 내역은 유지됩니다.")

    if st.button("🗑️ 현재 작업내역 지우기", use_container_width=True):
        st.session_state.match_state['completed'] = False
        st.rerun()


@st.cache_resource
def load_engine():
    return BrandMatchingSystem()


engine = load_engine()


# ==========================================
# 🚀 메인 화면 1: 발주서 자동 매칭
# ==========================================
if menu == "✅ 발주서 자동 매칭":
    st.title("🚀 2026 브랜드 매칭 시스템")
    st.markdown("---")

    uploaded_files = st.file_uploader(
        "발주 엑셀 파일 업로드", type=['xlsx', 'xls', 'csv'], accept_multiple_files=True
    )

    if uploaded_files:
        if st.button("🏁 통합 매칭 시작", use_container_width=True):
            try:
                dfs = []
                for file in uploaded_files:
                    if file.name.endswith('.csv'):
                        try:
                            df = pd.read_csv(file, encoding='utf-8')
                        except UnicodeDecodeError:
                            df = pd.read_csv(file, encoding='cp949')
                    else:
                        df = pd.read_excel(file)
                    df = df.dropna(how='all')
                    if not df.empty:
                        dfs.append(engine.convert_sheet1_to_sheet2(df))

                if not dfs:
                    st.warning("유효한 데이터가 없습니다.")
                    st.stop()

                combined_sheet2_df = pd.concat(dfs, ignore_index=True)
                total_input_rows = len(combined_sheet2_df)

                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(current, total):
                    progress_bar.progress(current / total)
                    status_text.markdown(
                        f"**진행률:** {int((current / total) * 100)}% ({current}건 / {total}건 처리 중)"
                    )

                with st.spinner("🤖 매칭 엔진 가동 중..."):
                    final_df, success_products, failed_products = engine.process_matching(
                        combined_sheet2_df, weights, progress_callback=update_progress
                    )

                st.session_state.match_state.update({
                    'final_df': final_df,
                    'success_products': success_products,
                    'failed_products': failed_products,
                    'completed': True,
                    'total_count': total_input_rows,
                    'success_count': len(success_products),
                    'fail_count': len(failed_products)
                })
                st.rerun()

            except Exception as e:
                st.error(f"오류: {e}")

    if st.session_state.match_state['completed']:
        s = st.session_state.match_state
        st.success("🎉 매칭 완료!")

        col1, col2, col3 = st.columns(3)
        col1.metric("총 발주 건수", f"{s['total_count']}건")
        col2.metric("매칭 성공", f"{s['success_count']}건")
        col3.metric("매칭 실패", f"{s['fail_count']}건")

        st.dataframe(s['final_df'].head(50))

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            s['final_df'].to_excel(writer, index=False, sheet_name='통합_전체_매칭결과')
            if s['success_products']:
                pd.DataFrame(s['success_products']).to_excel(writer, index=False, sheet_name='성공건_매칭상세')
            if s['failed_products']:
                pd.DataFrame(s['failed_products']).to_excel(writer, index=False, sheet_name='실패건_유사상품추천')

        st.download_button(
            "📥 통합 결과 다운로드 (상세포함)",
            data=output.getvalue(),
            file_name="매칭완료_상세리포트.xlsx",
            use_container_width=True
        )


# ==========================================
# 📚 서브 화면 2: 동의어/키워드 관리
# ==========================================
elif menu == "📚 동의어/키워드 관리":
    st.title("📚 스마트 동의어 및 제외 키워드 관리")
    tab1, tab2 = st.tabs(["📚 동의어 사전 관리", "✂️ 제외 키워드 관리"])

    with tab1:
        st.subheader("➕ 개별 등록")
        with st.form("synonym_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1: std_word = st.text_input("기준 단어 (정답)")
            with col2: syn_word = st.text_input("동의어 (오타)")
            st.markdown("📍 **적용 범위 및 강도**")
            c1, c2, c3, c4 = st.columns(4)
            b_app = c1.checkbox("브랜드", value=True)
            p_app = c2.checkbox("상품명", value=True)
            o_app = c3.checkbox("옵션", value=False)
            is_ex = c4.checkbox("완전일치", value=True)

            if st.form_submit_button("등록하기") and std_word and syn_word:
                # 개선: get_db() 컨텍스트 매니저 사용 → 세션 누수 방지
                with get_db() as db:
                    if db.query(Synonym).filter(Synonym.synonym_word == syn_word.strip()).first():
                        st.warning("🚨 이미 등록된 동의어입니다.")
                    else:
                        db.add(Synonym(
                            standard_word=std_word.strip(),
                            synonym_word=syn_word.strip(),
                            apply_brand=b_app,
                            apply_product=p_app,
                            apply_option=o_app,
                            is_exact_match=is_ex
                        ))
                        db.commit()
                        st.success("✅ 등록되었습니다!")
                        st.cache_resource.clear()
                        st.rerun()

        st.markdown("---")
        st.subheader("📥 엑셀 일괄 등록")
        col_down, col_up = st.columns([1, 2])

        with col_down:
            template_df = pd.DataFrame(columns=["기준단어", "동의어", "브랜드적용(O/X)", "상품명적용(O/X)", "옵션적용(O/X)", "완전일치(O/X)"])
            template_df.loc[0] = ["티셔츠", "티", "X", "O", "X", "O"]
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                template_df.to_excel(writer, index=False)
            st.download_button("📄 업로드 양식 다운로드", data=buffer.getvalue(),
                               file_name="동의어_일괄등록_양식.xlsx", use_container_width=True)

        with col_up:
            syn_excel = st.file_uploader("동의어 엑셀 파일을 업로드하세요", type=['xlsx'])
            if syn_excel and st.button("🚀 엑셀 데이터 일괄 저장", use_container_width=True):
                try:
                    df_upload = pd.read_excel(syn_excel)
                    # 개선: get_db() 컨텍스트 매니저 → 예외 시에도 세션 닫힘 보장
                    with get_db() as db:
                        existing_syns = {s.synonym_word for s in db.query(Synonym).all()}
                        count = 0
                        for _, row in df_upload.iterrows():
                            s_word = str(row.get('기준단어', '')).strip()
                            y_word = str(row.get('동의어', '')).strip()
                            if not s_word or not y_word or s_word == 'nan' or y_word == 'nan':
                                continue
                            if y_word in existing_syns:
                                continue
                            db.add(Synonym(
                                standard_word=s_word,
                                synonym_word=y_word,
                                apply_brand=str(row.get('브랜드적용(O/X)', '')).upper() == 'O',
                                apply_product=str(row.get('상품명적용(O/X)', '')).upper() == 'O',
                                apply_option=str(row.get('옵션적용(O/X)', '')).upper() == 'O',
                                is_exact_match=str(row.get('완전일치(O/X)', '')).upper() == 'O'
                            ))
                            existing_syns.add(y_word)
                            count += 1
                        db.commit()
                    st.success(f"✅ 중복/에러 없이 총 {count}건의 동의어가 성공적으로 일괄 등록되었습니다!")
                    st.cache_resource.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 오류가 발생했습니다: {e}")

        st.markdown("---")
        st.subheader("🗒️ 등록된 동의어 목록")

        # 개선: get_db() 컨텍스트 매니저 → 세션 누수 방지
        with get_db() as db:
            syns = db.query(Synonym).filter(Synonym.is_active == True).all()
            if syns:
                df_syns = pd.DataFrame([{
                    "선택": False, "정답": s.standard_word, "오타": s.synonym_word,
                    "브랜드": "O" if s.apply_brand else "X",
                    "상품명": "O" if s.apply_product else "X",
                    "옵션": "O" if s.apply_option else "X",
                    "완전일치": "O" if s.is_exact_match else "X"
                } for s in syns])

                edited_df = st.data_editor(
                    df_syns,
                    column_config={"선택": st.column_config.CheckboxColumn("삭제", default=False)},
                    hide_index=True, use_container_width=True
                )
                selected = edited_df[edited_df["선택"] == True]
                if not selected.empty:
                    if st.button("🗑️ 선택된 동의어 삭제하기"):
                        with get_db() as db2:
                            for target_syn in selected["오타"]:
                                to_del = db2.query(Synonym).filter(Synonym.synonym_word == target_syn).first()
                                if to_del:
                                    db2.delete(to_del)
                            db2.commit()
                        st.cache_resource.clear()
                        st.rerun()

    with tab2:
        with st.form("keyword_form", clear_on_submit=True):
            new_keyword = st.text_input("제외 키워드 입력")
            if st.form_submit_button("등록") and new_keyword:
                with get_db() as db:
                    if not db.query(Keyword).filter(Keyword.keyword_text == new_keyword.strip()).first():
                        db.add(Keyword(keyword_text=new_keyword.strip()))
                        db.commit()
                        st.success("✅ 등록!")
                        st.cache_resource.clear()
                        st.rerun()

        # 개선: get_db() 컨텍스트 매니저 → 세션 누수 방지
        with get_db() as db:
            kws = db.query(Keyword).all()
            if kws:
                df_kws = pd.DataFrame([{"선택": False, "키워드": k.keyword_text} for k in kws])
                edited_kw = st.data_editor(
                    df_kws,
                    column_config={"선택": st.column_config.CheckboxColumn("삭제", default=False)},
                    hide_index=True, use_container_width=True
                )
                sel_kw = edited_kw[edited_kw["선택"] == True]
                if not sel_kw.empty:
                    if st.button("🗑️ 선택된 키워드 삭제"):
                        with get_db() as db2:
                            for t_kw in sel_kw["키워드"]:
                                to_del = db2.query(Keyword).filter(Keyword.keyword_text == t_kw).first()
                                if to_del:
                                    db2.delete(to_del)
                            db2.commit()
                        st.cache_resource.clear()
                        st.rerun()


# ==========================================
# 📊 서브 화면 3: DB 상태
# ==========================================
elif menu == "📊 DB 연동 상태":
    st.title("📊 마스터 DB 연동 및 검색 관리")

    if engine.brand_data is not None and not engine.brand_data.empty:
        st.success(f"🟢 AWS DB 연결 완료 (총 {len(engine.brand_data):,}건 데이터)")
    else:
        st.warning("⚠️ DB에 데이터가 없거나 연결에 실패했습니다.")

    tab_search, tab_date, tab_upload = st.tabs([
        "🔍 검색 및 삭제",
        "📅 날짜별 관리",
        "📥 신규 DB 업로드"
    ])

    # ──────────────────────────────────────────
    # 탭 1: 검색 및 체크박스 삭제
    # ──────────────────────────────────────────
    with tab_search:
        if 'master_search_query' not in st.session_state:
            st.session_state.master_search_query = ''

        with st.form("search_form"):
            search_input = st.text_input(
                "🔍 브랜드 또는 상품명 검색",
                value=st.session_state.master_search_query,
                placeholder="검색어 입력 후 검색 실행"
            )
            col_s1, col_s2 = st.columns([3, 1])
            search_submit = col_s1.form_submit_button("🔍 검색 실행", use_container_width=True)
            clear_submit = col_s2.form_submit_button("초기화", use_container_width=True)

        if search_submit:
            st.session_state.master_search_query = search_input.strip()
        elif clear_submit:
            st.session_state.master_search_query = ''

        search_query = st.session_state.master_search_query

        if search_query:
            with get_db() as db:
                results = db.query(MasterProduct).filter(
                    or_(
                        MasterProduct.brand.ilike(f'%{search_query}%'),
                        MasterProduct.product_name.ilike(f'%{search_query}%')
                    )
                ).order_by(MasterProduct.brand, MasterProduct.product_name).limit(500).all()

            if results:
                st.write(f"**검색 결과:** {len(results)}건 (최대 500건 표시)")
                df_results = pd.DataFrame([{
                    "선택": False,
                    "ID": r.id,
                    "브랜드": r.brand or '',
                    "상품명": r.product_name or '',
                    "옵션": r.options or '',
                    "중도매": r.wholesale_name or '',
                    "공급가": r.supply_price or 0,
                    "업로드일": r.uploaded_at.strftime('%Y-%m-%d') if r.uploaded_at else "미기록"
                } for r in results])

                edited_search = st.data_editor(
                    df_results,
                    column_config={
                        "선택": st.column_config.CheckboxColumn("삭제선택", default=False),
                        "ID": st.column_config.NumberColumn("ID", disabled=True),
                        "브랜드": st.column_config.TextColumn("브랜드", disabled=True),
                        "상품명": st.column_config.TextColumn("상품명", disabled=True),
                        "옵션": st.column_config.TextColumn("옵션", disabled=True),
                        "중도매": st.column_config.TextColumn("중도매", disabled=True),
                        "공급가": st.column_config.NumberColumn("공급가", disabled=True),
                        "업로드일": st.column_config.TextColumn("업로드일", disabled=True),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="search_result_editor"
                )

                selected_ids = edited_search[edited_search["선택"] == True]["ID"].tolist()
                if selected_ids:
                    st.warning(f"⚠️ {len(selected_ids)}건이 선택되었습니다. 삭제하면 복구할 수 없습니다.")
                    if st.button(f"🗑️ 선택된 {len(selected_ids)}건 삭제", key="btn_delete_search", type="primary"):
                        with get_db() as db2:
                            deleted_count = db2.query(MasterProduct).filter(
                                MasterProduct.id.in_(selected_ids)
                            ).delete(synchronize_session=False)
                            db2.commit()
                        st.success(f"✅ {deleted_count}건 삭제 완료!")
                        st.session_state.master_search_query = ''
                        st.cache_resource.clear()
                        st.rerun()
            else:
                st.info("검색 결과가 없습니다.")
        else:
            st.info("검색어를 입력하고 '검색 실행'을 눌러주세요.")

    # ──────────────────────────────────────────
    # 탭 2: 날짜별 조회 및 삭제
    # ──────────────────────────────────────────
    with tab_date:
        st.subheader("📅 업로드 날짜별 데이터 관리")
        st.caption("날짜를 선택(체크)하고 삭제 버튼을 누르면 해당 날짜의 데이터가 모두 삭제됩니다.")

        with get_db() as db:
            date_counts = db.query(
                cast(MasterProduct.uploaded_at, SADate).label('upload_date'),
                func.count(MasterProduct.id).label('count')
            ).group_by(
                cast(MasterProduct.uploaded_at, SADate)
            ).order_by(
                cast(MasterProduct.uploaded_at, SADate).desc().nullslast()
            ).all()

        if date_counts:
            df_dates = pd.DataFrame([{
                "선택": False,
                "업로드 날짜": str(d.upload_date) if d.upload_date else "날짜 미기록",
                "건수": d.count
            } for d in date_counts])

            edited_dates = st.data_editor(
                df_dates,
                column_config={
                    "선택": st.column_config.CheckboxColumn("삭제선택", default=False),
                    "업로드 날짜": st.column_config.TextColumn("업로드 날짜", disabled=True),
                    "건수": st.column_config.NumberColumn("건수", disabled=True),
                },
                hide_index=True,
                use_container_width=True,
                key="date_editor"
            )

            selected_date_rows = edited_dates[edited_dates["선택"] == True]
            if not selected_date_rows.empty:
                total_to_delete = int(selected_date_rows["건수"].sum())
                selected_date_labels = selected_date_rows["업로드 날짜"].tolist()
                st.warning(f"⚠️ {len(selected_date_labels)}개 날짜, 총 {total_to_delete:,}건이 선택되었습니다.")

                if st.button(
                    f"🗑️ 선택 날짜 {len(selected_date_labels)}일 ({total_to_delete:,}건) 전체 삭제",
                    key="btn_delete_by_date",
                    type="primary"
                ):
                    with get_db() as db2:
                        deleted_total = 0
                        for date_label in selected_date_labels:
                            if date_label == "날짜 미기록":
                                cnt = db2.query(MasterProduct).filter(
                                    MasterProduct.uploaded_at == None
                                ).delete(synchronize_session=False)
                            else:
                                from datetime import date as pydate
                                target_date = pydate.fromisoformat(date_label)
                                cnt = db2.query(MasterProduct).filter(
                                    cast(MasterProduct.uploaded_at, SADate) == target_date
                                ).delete(synchronize_session=False)
                            deleted_total += cnt
                        db2.commit()
                    st.success(f"✅ 총 {deleted_total:,}건 삭제 완료!")
                    st.cache_resource.clear()
                    st.rerun()

            # 날짜 클릭 시 해당 날짜 데이터 미리보기
            st.markdown("---")
            st.subheader("🔎 날짜별 데이터 미리보기")
            preview_dates = [str(d.upload_date) if d.upload_date else "날짜 미기록" for d in date_counts]
            selected_preview = st.selectbox("미리볼 날짜 선택", options=preview_dates, key="date_preview_select")
            if selected_preview:
                with get_db() as db:
                    if selected_preview == "날짜 미기록":
                        preview_records = db.query(MasterProduct).filter(
                            MasterProduct.uploaded_at == None
                        ).limit(200).all()
                    else:
                        from datetime import date as pydate
                        preview_date = pydate.fromisoformat(selected_preview)
                        preview_records = db.query(MasterProduct).filter(
                            cast(MasterProduct.uploaded_at, SADate) == preview_date
                        ).limit(200).all()

                if preview_records:
                    df_preview = pd.DataFrame([{
                        "브랜드": r.brand or '',
                        "상품명": r.product_name or '',
                        "옵션": r.options or '',
                        "중도매": r.wholesale_name or '',
                        "공급가": r.supply_price or 0,
                    } for r in preview_records])
                    st.write(f"**{selected_preview}** 데이터 미리보기 ({len(preview_records)}건, 최대 200건 표시)")
                    st.dataframe(df_preview, use_container_width=True)
        else:
            st.info("업로드된 데이터가 없습니다.")

    # ──────────────────────────────────────────
    # 탭 3: 신규 마스터 DB 업로드 (기존 기능 유지)
    # ──────────────────────────────────────────
    with tab_upload:
        st.subheader("📥 신규 마스터 DB 업로드")
        db_upload_file = st.file_uploader("마스터 DB 엑셀 파일 업로드", type=['xlsx'], key="master_db_uploader")
        if db_upload_file and st.button("🚀 DB에 추가", key="btn_db_add"):
            try:
                new_db = pd.read_excel(db_upload_file)
                upload_time = datetime.utcnow()
                # 개선: get_db() 컨텍스트 매니저 + 중복 체크 추가
                with get_db() as db:
                    # 기존 (브랜드+상품명+옵션) 조합으로 중복 키 생성
                    existing_keys = set()
                    for prod in db.query(
                        MasterProduct.brand,
                        MasterProduct.product_name,
                        MasterProduct.options
                    ).all():
                        existing_keys.add((
                            str(prod.brand or '').strip(),
                            str(prod.product_name or '').strip(),
                            str(prod.options or '').strip()
                        ))

                    count = 0
                    skip_count = 0
                    for _, r in new_db.iterrows():
                        b_val = str(r.get('브랜드', '')).strip()
                        if not b_val or b_val == 'nan':
                            continue
                        p_val = str(r.get('상품명', '')).strip()
                        o_val = str(r.get('옵션입력', '')).strip()
                        key = (b_val, p_val, o_val)

                        # 개선: 중복 체크 → 동일 데이터 재업로드 시 2배 증가 방지
                        if key in existing_keys:
                            skip_count += 1
                            continue

                        existing_keys.add(key)
                        raw_price = str(r.get('공급가', '0')).replace(',', '').strip()
                        try:
                            price_val = float(raw_price)
                        except ValueError:
                            price_val = 0.0

                        db.add(MasterProduct(
                            brand=b_val,
                            product_name=p_val,
                            options=o_val,
                            wholesale_name=str(r.get('중도매', '')).strip(),
                            supply_price=price_val,
                            uploaded_at=upload_time
                        ))
                        count += 1

                    db.commit()

                msg = f"✅ 총 {count}건 업로드 완료!"
                if skip_count > 0:
                    msg += f" (중복 {skip_count}건 자동 제외됨)"
                st.success(msg)
                st.cache_resource.clear()
                st.rerun()
            except Exception as e:
                st.error(f"오류: {e}")
