# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy_financial as npf
import docx
import re
import io

# ======================================================================================
# PHẦN 1: CÁC HÀM TIỆN ÍCH VÀ XỬ LÝ DỮ LIỆU
# ======================================================================================

def read_word_file(uploaded_file):
    """
    Đọc nội dung từ file Word (docx) do người dùng tải lên.
    """
    try:
        # Sử dụng BytesIO để đọc file từ bộ nhớ thay vì từ đĩa
        doc = docx.Document(io.BytesIO(uploaded_file.getvalue()))
        full_text = [para.text for para in doc.paragraphs]
        return '\n'.join(full_text)
    except Exception as e:
        st.error(f"Lỗi khi đọc file Word: {e}")
        return None

def extract_info_from_text_mock(text):
    """
    *** PHIÊN BẢN GIẢ LẬP (MOCK) ***
    Sử dụng AI (ở đây là regex giả lập) để trích xuất thông tin tài chính từ văn bản.
    Trong thực tế, bạn sẽ thay thế hàm này bằng một lời gọi đến API của một mô hình ngôn ngữ lớn (LLM) như Gemini.
    """
    # Hàm trợ giúp để tìm số liệu
    def find_value(pattern, text_content):
        match = re.search(pattern, text_content, re.IGNORECASE)
        if match:
            # Lấy chuỗi số và loại bỏ các ký tự không phải số
            numeric_string = re.sub(r'[^\d.]', '', match.group(1))
            return float(numeric_string) if '.' in numeric_string else int(numeric_string)
        return None

    # Các mẫu regex để tìm kiếm thông tin
    # Lưu ý: Các mẫu này rất cơ bản và cần được cải thiện để hoạt động tốt hơn
    patterns = {
        'investment': r"(?:vốn đầu tư|đầu tư ban đầu|tổng vốn đầu tư|investment)\s*[:\s]*([\d,.]+)\s*(?:tỷ|triệu|đồng|usd)",
        'lifespan': r"(?:vòng đời dự án|thời gian dự án|dòng đời dự án|lifespan)\s*[:\s]*(\d+)\s*năm",
        'revenue': r"(?:doanh thu hàng năm|doanh thu dự kiến|revenue)\s*[:\s]*([\d,.]+)\s*(?:tỷ|triệu|đồng|usd)",
        'cost': r"(?:chi phí hàng năm|tổng chi phí|cost)\s*[:\s]*([\d,.]+)\s*(?:tỷ|triệu|đồng|usd)",
        'wacc': r"(?:wacc|suất chiết khấu|chi phí vốn bình quân)\s*[:\s]*([\d.]+)%",
        'tax': r"(?:thuế suất|thuế thu nhập doanh nghiệp|tax)\s*[:\s]*([\d.]+)%"
    }

    # Trích xuất thông tin
    project_info = {}
    for key, pattern in patterns.items():
        project_info[key] = find_value(pattern, text)

    # Chuyển đổi WACC và tax về dạng số thập phân
    if project_info.get('wacc'):
        project_info['wacc'] /= 100
    if project_info.get('tax'):
        project_info['tax'] /= 100

    # Cung cấp giá trị mặc định nếu không tìm thấy để tránh lỗi
    defaults = {
        'investment': 1000, 'lifespan': 5, 'revenue': 500,
        'cost': 200, 'wacc': 0.12, 'tax': 0.20
    }
    for key, value in defaults.items():
        if project_info.get(key) is None:
            st.warning(f"Không tìm thấy thông tin '{key}', sử dụng giá trị mặc định: {value}")
            project_info[key] = value

    return project_info

def calculate_cash_flow(info):
    """
    Xây dựng bảng dòng tiền của dự án dựa trên thông tin đã trích xuất.
    """
    if not all(k in info for k in ['investment', 'lifespan', 'revenue', 'cost', 'tax']):
        st.error("Thiếu thông tin cần thiết để tính toán dòng tiền.")
        return None

    years = range(info['lifespan'] + 1)
    # Khởi tạo các dòng trong bảng dòng tiền
    revenue = [0] + [info['revenue']] * info['lifespan']
    cost = [0] + [info['cost']] * info['lifespan']

    df_data = {
        'Doanh thu': revenue,
        'Chi phí': cost
    }
    df = pd.DataFrame(df_data, index=years)
    df.index.name = "Năm"

    df['Lợi nhuận trước thuế (EBT)'] = df['Doanh thu'] - df['Chi phí']
    df['Thuế (EBT * thuế suất)'] = df['Lợi nhuận trước thuế (EBT)'] * info['tax']
    # Đảm bảo thuế không âm
    df['Thuế (EBT * thuế suất)'] = df['Thuế (EBT * thuế suất)'].apply(lambda x: max(x, 0))
    df['Lợi nhuận sau thuế (EAT)'] = df['Lợi nhuận trước thuế (EBT)'] - df['Thuế (EBT * thuế suất)']
    
    # Dòng tiền thuần (Net Cash Flow - NCF)
    # Giả định đơn giản: NCF = Lợi nhuận sau thuế (không có khấu hao)
    # Năm 0 chỉ có chi phí đầu tư
    df['Dòng tiền thuần (NCF)'] = df['Lợi nhuận sau thuế (EAT)']
    df.loc[0, 'Dòng tiền thuần (NCF)'] = -info['investment']

    return df


def calculate_metrics(cash_flow_df, wacc):
    """
    Tính toán các chỉ số hiệu quả dự án: NPV, IRR, PP, DPP.
    """
    if cash_flow_df is None or 'Dòng tiền thuần (NCF)' not in cash_flow_df.columns:
        return {}
        
    cash_flows = cash_flow_df['Dòng tiền thuần (NCF)'].values
    
    # 1. NPV - Hiện giá thuần
    try:
        npv = npf.npv(wacc, cash_flows)
    except Exception:
        npv = "Không thể tính toán"

    # 2. IRR - Tỷ suất hoàn vốn nội bộ
    try:
        irr = npf.irr(cash_flows)
        irr = f"{irr:.2%}"
    except Exception:
        irr = "Không thể tính toán"
        
    # 3. PP - Thời gian hoàn vốn
    cumulative_cash_flow = cash_flows.cumsum()
    try:
        payback_period_year = next(i for i, v in enumerate(cumulative_cash_flow) if v >= 0)
        last_negative_year = payback_period_year - 1
        pp = last_negative_year + abs(cumulative_cash_flow[last_negative_year]) / cash_flows[payback_period_year]
        pp = f"{pp:.2f} năm"
    except StopIteration:
        pp = "Không hoàn vốn trong đời dự án"

    # 4. DPP - Thời gian hoàn vốn có chiết khấu
    discounted_flows = [cf / ((1 + wacc) ** i) for i, cf in enumerate(cash_flows)]
    cumulative_discounted_cash_flow = pd.Series(discounted_flows).cumsum().values
    try:
        d_payback_period_year = next(i for i, v in enumerate(cumulative_discounted_cash_flow) if v >= 0)
        d_last_negative_year = d_payback_period_year - 1
        dpp = d_last_negative_year + abs(cumulative_discounted_cash_flow[d_last_negative_year]) / discounted_flows[d_payback_period_year]
        dpp = f"{dpp:.2f} năm"
    except StopIteration:
        dpp = "Không hoàn vốn trong đời dự án"

    return {'NPV': npv, 'IRR': irr, 'PP': pp, 'DPP': dpp}

def analyze_metrics_with_ai_mock(metrics, info):
    """
    *** PHIÊN BẢN GIẢ LẬP (MOCK) ***
    Sử dụng AI (ở đây là logic if-else) để phân tích các chỉ số.
    Trong thực tế, bạn sẽ tạo một prompt chi tiết gửi đến Gemini API cùng với các chỉ số này.
    """
    if not metrics:
        return "Không có chỉ số để phân tích."

    npv = metrics.get('NPV', 0)
    irr_str = metrics.get('IRR', '0%')
    try:
        # Chuyển IRR từ chuỗi "12.34%" về số 0.1234
        irr_val = float(irr_str.strip('%'))/100
    except (ValueError, TypeError):
        irr_val = -999 # Giá trị lỗi

    wacc = info.get('wacc', 0.1)

    analysis = "### Phân Tích Sơ Bộ Về Hiệu Quả Dự Án\n\n"

    # Phân tích NPV
    analysis += "**1. Hiện giá thuần (NPV):**\n"
    if isinstance(npv, (int, float)):
        if npv > 0:
            analysis += f"- **Tích cực:** NPV > 0 ({npv:,.2f}) cho thấy dự án dự kiến sẽ tạo ra giá trị cho nhà đầu tư, sau khi đã tính đến chi phí cơ hội của vốn (WACC). Đây là một dấu hiệu tốt cho thấy dự án có khả năng sinh lời.\n"
        elif npv == 0:
            analysis += f"- **Trung tính:** NPV = 0. Dự án dự kiến chỉ đủ bù đắp chi phí vốn. Nhà đầu tư có thể cân nhắc các cơ hội khác có tiềm năng sinh lời cao hơn.\n"
        else:
            analysis += f"- **Tiêu cực:** NPV < 0 ({npv:,.2f}). Dự án dự kiến sẽ làm giảm giá trị của nhà đầu tư. Cần xem xét lại các giả định về doanh thu, chi phí hoặc có thể từ chối dự án.\n"
    else:
        analysis += "- Không thể tính toán NPV. Cần kiểm tra lại dòng tiền của dự án.\n"

    # Phân tích IRR
    analysis += "\n**2. Tỷ suất hoàn vốn nội bộ (IRR):**\n"
    if irr_val != -999:
        analysis += f"- IRR của dự án là **{irr_str}**, so với chi phí sử dụng vốn (WACC) là **{wacc:.2%}**.\n"
        if irr_val > wacc:
            analysis += f"- **Tích cực:** IRR > WACC. Điều này có nghĩa là tỷ suất sinh lời nội tại của dự án cao hơn chi phí vốn, củng cố thêm cho quyết định đầu tư. Mức chênh lệch càng lớn, dự án càng hấp dẫn.\n"
        else:
            analysis += f"- **Tiêu cực:** IRR <= WACC. Tỷ suất sinh lời của dự án không đủ để bù đắp chi phí vốn. Dự án không hấp dẫn về mặt tài chính.\n"
    else:
        analysis += "- Không thể tính toán IRR. Thường xảy ra khi dòng tiền không đổi dấu hoặc có nhiều lần đổi dấu phức tạp.\n"

    # Phân tích PP và DPP
    analysis += "\n**3. Thời gian hoàn vốn (PP & DPP):**\n"
    analysis += f"- Thời gian hoàn vốn (PP) là **{metrics.get('PP', 'N/A')}** và thời gian hoàn vốn có chiết khấu (DPP) là **{metrics.get('DPP', 'N/A')}**.\n"
    analysis += "- PP cho biết mất bao lâu để dòng tiền thu vào bù đắp được vốn đầu tư ban đầu. DPP thực tế hơn vì nó tính đến giá trị thời gian của tiền.\n"
    analysis += "- Nhà đầu tư thường so sánh các chỉ số này với một ngưỡng yêu cầu (ví dụ: mong muốn hoàn vốn trong 3 năm). Thời gian hoàn vốn càng ngắn, rủi ro thanh khoản càng thấp.\n"

    analysis += "\n---\n"
    analysis += "**Khuyến nghị tổng quát:** Dựa trên các phân tích trên, dự án này **"
    if isinstance(npv, (int, float)) and npv > 0 and irr_val > wacc:
        analysis += "có vẻ khả thi về mặt tài chính.** Tuy nhiên, cần lưu ý rằng đây chỉ là phân tích dựa trên các giả định đầu vào. Cần thực hiện thêm các phân tích độ nhạy và kịch bản để đánh giá rủi ro."
    else:
        analysis += "có vẻ không khả thi về mặt tài chính.** Cần xem xét lại các yếu tố cốt lõi như dự báo doanh thu, cấu trúc chi phí, hoặc các rủi ro tiềm ẩn chưa được tính đến."
        
    return analysis

# ======================================================================================
# PHẦN 2: GIAO DIỆN NGƯỜI DÙNG (STREAMLIT UI)
# ======================================================================================

def main():
    st.set_page_config(page_title="Phân Tích Phương Án Kinh Doanh", layout="wide")

    # --- Giao diện chính ---
    st.title("Ứng dụng Phân tích Phương án Kinh doanh bằng AI")
    st.markdown("""
        Chào mừng bạn đến với công cụ phân tích hiệu quả dự án đầu tư.
        Hãy tải lên file Word (`.docx`) chứa phương án kinh doanh của bạn.
        AI sẽ tự động trích xuất các thông số chính và tính toán các chỉ số quan trọng.
    """)

    # --- Khu vực tải file và khởi tạo session state ---
    uploaded_file = st.file_uploader("Chọn file Word (.docx)", type="docx")

    if 'analysis_done' not in st.session_state:
        st.session_state.analysis_done = False
    if 'project_info' not in st.session_state:
        st.session_state.project_info = None
    if 'cash_flow_df' not in st.session_state:
        st.session_state.cash_flow_df = None
    if 'metrics' not in st.session_state:
        st.session_state.metrics = None
    if 'ai_analysis' not in st.session_state:
        st.session_state.ai_analysis = ""


    if uploaded_file is not None:
        # Đọc nội dung file
        text_content = read_word_file(uploaded_file)

        if text_content:
            # Nút bấm để thực hiện trích xuất dữ liệu
            if st.button("1. Dùng AI để trích xuất thông tin", type="primary"):
                with st.spinner("AI đang làm việc, vui lòng chờ..."):
                    st.session_state.project_info = extract_info_from_text_mock(text_content)
                    st.session_state.analysis_done = True
                    # Reset các bước sau nếu thực hiện lại bước 1
                    st.session_state.cash_flow_df = None
                    st.session_state.metrics = None
                    st.session_state.ai_analysis = ""


            if st.session_state.analysis_done and st.session_state.project_info:
                st.subheader("Kết quả trích xuất thông tin dự án")
                st.json(st.session_state.project_info)

                # --- Bước 2: Xây dựng bảng dòng tiền ---
                st.header("2. Bảng Dòng Tiền Dự Án")
                if st.session_state.cash_flow_df is None:
                     st.session_state.cash_flow_df = calculate_cash_flow(st.session_state.project_info)

                if st.session_state.cash_flow_df is not None:
                    # Định dạng lại bảng để dễ đọc hơn
                    st.dataframe(st.session_state.cash_flow_df.style.format("{:,.0f}"))
                
                    # --- Bước 3: Tính toán các chỉ số ---
                    st.header("3. Các Chỉ Số Đánh Giá Hiệu Quả Dự Án")
                    if st.session_state.metrics is None:
                        st.session_state.metrics = calculate_metrics(st.session_state.cash_flow_df, st.session_state.project_info['wacc'])
                    
                    if st.session_state.metrics:
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            npv_val = st.session_state.metrics['NPV']
                            st.metric(label="Hiện giá thuần (NPV)", value=f"{npv_val:,.0f}" if isinstance(npv_val, (int, float)) else npv_val)
                        with col2:
                            st.metric(label="Tỷ suất hoàn vốn nội bộ (IRR)", value=st.session_state.metrics['IRR'])
                        with col3:
                            st.metric(label="Thời gian hoàn vốn (PP)", value=st.session_state.metrics['PP'])
                        with col4:
                            st.metric(label="Thời gian hoàn vốn có chiết khấu (DPP)", value=st.session_state.metrics['DPP'])

                        # --- Bước 4: Phân tích của AI ---
                        st.header("4. Phân Tích Chuyên Sâu từ AI")
                        if st.button("Yêu cầu AI phân tích các chỉ số", type="primary"):
                             with st.spinner("AI đang phân tích sâu hơn..."):
                                st.session_state.ai_analysis = analyze_metrics_with_ai_mock(st.session_state.metrics, st.session_state.project_info)
                        
                        if st.session_state.ai_analysis:
                            st.markdown(st.session_state.ai_analysis)

if __name__ == "__main__":
    main()
