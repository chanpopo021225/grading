import streamlit as st
import pandas as pd
import io
import time
import json
import os
from datetime import datetime
from pathlib import Path

# --- 配置持久化存储 ---
SAVE_DIR = Path(".essay_grades")
SAVE_FILE = SAVE_DIR / "auto_save.json"

# 确保保存目录存在
if not SAVE_DIR.exists():
    SAVE_DIR.mkdir(exist_ok=True)

# --- 页面基础设置 ---
st.set_page_config(
    page_title="英语作文交互式批改工具",
    page_icon="✍️",
    layout="wide"
)

st.title("✍️ 英语作文交互式批改工具")

# --- 初始化 Session State ---
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'scores' not in st.session_state:
    st.session_state.scores = {}
if 'df' not in st.session_state:
    st.session_state.df = None
# 初始化作文题目存储
if 'essay_prompt' not in st.session_state:
    st.session_state.essay_prompt = ""
# 初始化分数点击状态
for score in range(16):
    if f"score_clicked_{score}" not in st.session_state:
        st.session_state[f"score_clicked_{score}"] = False
# 自动保存相关状态
if 'last_saved_time' not in st.session_state:
    st.session_state.last_saved_time = None
if 'save_counter' not in st.session_state:
    st.session_state.save_counter = 0  # 用于触发重绘的计数器
if 'saved_scores' not in st.session_state:
    st.session_state.saved_scores = None  # 用于存储已保存的分数备份
if 'file_hash' not in st.session_state:
    st.session_state.file_hash = None  # 用于识别不同的上传文件

# --- 持久化保存功能 ---
def save_to_file():
    """将当前状态保存到本地文件"""
    if st.session_state.df is not None and st.session_state.scores:
        # 准备要保存的数据
        save_data = {
            "scores": st.session_state.scores,
            "essay_prompt": st.session_state.essay_prompt,
            "current_index": st.session_state.current_index,
            "file_hash": st.session_state.file_hash,
            "saved_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 写入本地文件
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        return True
    return False

def load_from_file():
    """从本地文件加载保存的状态"""
    if SAVE_FILE.exists():
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                save_data = json.load(f)
            
            # 只有当加载的文件与当前文件匹配时才恢复数据
            if (st.session_state.file_hash and 
                save_data.get("file_hash") == st.session_state.file_hash):
                
                st.session_state.scores = save_data["scores"]
                st.session_state.essay_prompt = save_data.get("essay_prompt", "")
                st.session_state.current_index = save_data.get("current_index", 0)
                st.session_state.last_saved_time = save_data.get("saved_time", "").split(" ")[1]
                st.session_state.saved_scores = save_data["scores"].copy()
                
                return True
        except Exception as e:
            st.warning(f"加载保存数据失败: {e}")
    
    return False

def save_progress():
    """保存当前评分进度（内存+文件）"""
    if st.session_state.df is not None and st.session_state.scores:
        # 保存到内存
        st.session_state.saved_scores = st.session_state.scores.copy()
        st.session_state.last_saved_time = datetime.now().strftime("%H:%M:%S")
        st.session_state.save_counter += 1
        
        # 同时保存到本地文件
        if save_to_file():
            return True
    return False

def auto_save_callback():
    """定时自动保存的回调函数"""
    if st.session_state.df is not None:
        # 只有当分数有变化时才保存
        if st.session_state.saved_scores != st.session_state.scores:
            save_progress()

# --- 尝试加载之前保存的数据 ---
if st.session_state.df is None and SAVE_FILE.exists():
    # 显示恢复选项
    if st.sidebar.button("🔄 恢复上次批改进度"):
        # 先标记为需要恢复（实际恢复在文件上传后进行）
        st.session_state.restore_on_load = True
        st.sidebar.info("请重新上传相同的Excel文件以恢复进度")

# 设置定时回调（每30秒自动保存一次）
if st.session_state.df is not None:
    st_autorefresh = st.empty()
    st_autorefresh.markdown(
        f"""
        <script>
        setInterval(function() {{
            // 触发Streamlit回调
            window.parent.document.querySelector('button[title="Rerun"]').click();
        }}, 30000);  // 30000毫秒 = 30秒
        </script>
        """,
        unsafe_allow_html=True
    )
    # 执行自动保存检查
    auto_save_callback()

# --- 输入作文题目 ---
st.header("第一步：输入作文题目")
prompt_input = st.text_area(
    "在此处粘贴或输入本次作文的题目和要求：",
    height=150,
    value=st.session_state.essay_prompt,
    help="在这里输入作文题目、写作要求、字数限制等信息。"
)
if prompt_input != st.session_state.essay_prompt:
    st.session_state.essay_prompt = prompt_input
    save_progress()  # 题目变更时立即保存


st.header("第二步：上传学生作文文件")
st.write("请在下方上传包含学生作文信息的 XLSX 文件开始批改。")
uploaded_file = st.file_uploader("上传XLSX文件", type=["xlsx"])

if uploaded_file is not None:
    try:
        temp_df = pd.read_excel(uploaded_file)
        
        # 计算文件哈希值用于识别
        file_hash = hash(pd.util.hash_pandas_object(temp_df).sum())
        st.session_state.file_hash = file_hash
        
        if st.session_state.df is None or not st.session_state.df.equals(temp_df):
            df = temp_df
            required_columns = ['学生作答图片1', '学生作答图片2', '评分标准']
            if not all(col in df.columns for col in required_columns):
                st.error(f"上传的文件缺少必要的列。请确保文件包含以下中文列: {', '.join(required_columns)}")
                st.stop()
            
            st.session_state.df = df
            st.session_state.current_index = 0
            st.session_state.scores = [-1] * len(df)
            st.session_state.saved_scores = [-1] * len(df)  # 初始化保存的分数
            
            # 如果用户要求恢复进度，尝试加载
            if hasattr(st.session_state, 'restore_on_load') and st.session_state.restore_on_load:
                if load_from_file():
                    st.success("文件加载成功，已恢复上次批改进度！")
                    del st.session_state.restore_on_load
                else:
                    st.success("文件加载成功，但未找到匹配的保存进度！")
            else:
                st.success("文件加载成功！现在可以开始批改。")
            
            save_progress()  # 新文件加载后立即保存
            st.rerun()
    except Exception as e:
        st.error(f"文件读取失败: {e}")
        st.stop()

# --- 主批改界面 ---
if st.session_state.df is not None:
    df = st.session_state.df
    total_students = len(df)
    
    if st.session_state.current_index >= total_students:
        st.session_state.current_index = 0

    current_student = df.iloc[st.session_state.current_index]

    col1, col2 = st.columns([3, 1])

    with col1:
        st.header(f"批改中：第 {st.session_state.current_index + 1} / {total_students} 份")
        
        # 显示保存状态
        if st.session_state.last_saved_time:
            st.info(f"最后保存时间: {st.session_state.last_saved_time} | 数据已备份到本地文件")
        
        if st.session_state.essay_prompt:
            with st.expander("📌 查看作文题目", expanded=True):
                st.markdown(st.session_state.essay_prompt)
        
        with st.expander("📝 点击查看评分标准", expanded=False):
            st.markdown(current_student['评分标准'])

        st.subheader("学生作答图片 1")
        st.image(current_student['学生作答图片1'], use_container_width=True)

        st.subheader("学生作答图片 2")
        st.image(current_student['学生作答图片2'], use_container_width=True)
        
    with col2:
        st.header("评分操作区")

        tier_options = {
            "差 (2分档)": 2,
            "中下 (5分档)": 5,
            "中等 (8分档)": 8,
            "中上 (11分档)": 11,
            "优 (14分档)": 14
        }
        
        selected_tier_label = st.radio(
            "第一步：选择评分档位",
            options=tier_options.keys(),
            key=f"tier_radio_{st.session_state.current_index}"
        )
        
        default_score = tier_options[selected_tier_label]

        current_score_val = st.session_state.scores[st.session_state.current_index]
        
        # 点击式分数块
        st.write("第二步：选择具体分数 (0-15分)")
        
        # 确定默认值
        if current_score_val == -1:
            score_value = default_score
        else:
            score_value = int(current_score_val)
        
        # 处理分数点击事件
        for score in range(16):
            if st.session_state[f"score_clicked_{score}"]:
                score_value = score
                st.session_state.scores[st.session_state.current_index] = score_value
                # 重置所有分数点击状态
                for s in range(16):
                    st.session_state[f"score_clicked_{s}"] = False
                save_progress()  # 分数变更时立即保存
                st.rerun()
        
        # 创建分数块，每行显示5个分数
        cols_per_row = 5
        for i in range(0, 16, cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                score = i + j
                if score > 15:
                    break
                
                # 设置按钮样式
                if score == score_value:
                    # 选中状态
                    btn_kwargs = {
                        "use_container_width": True,
                        "type": "primary"
                    }
                else:
                    # 未选中状态
                    btn_kwargs = {
                        "use_container_width": True,
                        "type": "secondary"
                    }
                
                # 使用Streamlit按钮组件（可点击）
                with cols[j]:
                    if st.button(
                        str(score),
                        key=f"score_btn_{score}_{st.session_state.current_index}",** btn_kwargs
                    ):
                        st.session_state[f"score_clicked_{score}"] = True
                        st.rerun()
        
        # 保存当前选择的分数
        if st.session_state.scores[st.session_state.current_index] != score_value:
            st.session_state.scores[st.session_state.current_index] = score_value
            save_progress()  # 分数变更时立即保存

        st.metric(label="当前作文最终得分", value=f"{score_value} 分")

        # 手动保存按钮
        if st.button("💾 手动保存当前进度", use_container_width=True):
            if save_progress():
                st.success("进度已保存到本地文件！")

        nav_col1, nav_col2, nav_col3 = st.columns(3)
        with nav_col1:
            if st.button("⬅️ 上一份", use_container_width=True, disabled=(st.session_state.current_index == 0)):
                st.session_state.current_index -= 1
                st.rerun()

        with nav_col2:
            if st.button("下一份 ➡️", use_container_width=True, disabled=(st.session_state.current_index >= total_students - 1)):
                st.session_state.current_index += 1
                st.rerun()
        
        with nav_col3:
            jump_to = st.number_input(
                "跳转至", 
                min_value=1, 
                max_value=total_students, 
                value=st.session_state.current_index + 1,
                step=1,
                label_visibility="collapsed",
                key=f"jump_{st.session_state.current_index}"
            )
            if jump_to != st.session_state.current_index + 1:
                st.session_state.current_index = jump_to - 1
                st.rerun()

    # --- 导出功能 ---
    st.sidebar.header("完成与导出")
    progress_text = f"已批改 {len([s for s in st.session_state.scores if s != -1])} / {total_students} 份"
    st.sidebar.progress(len([s for s in st.session_state.scores if s != -1]) / total_students, text=progress_text)
    
    # 显示自动保存状态
    if st.session_state.last_saved_time:
        st.sidebar.info(f"自动保存: 最后保存于 {st.session_state.last_saved_time}")
    else:
        st.sidebar.info("尚未保存进度")

    # 本地备份文件位置信息
    st.sidebar.caption(f"备份文件位置: {SAVE_FILE.absolute()}")

    if st.sidebar.button("导出批改结果"):
        result_df = df.copy()
        result_df['得分'] = st.session_state.scores
        result_df['得分'] = result_df['得分'].apply(lambda x: "未批改" if x == -1 else x)
        
        result_df['作文题目'] = st.session_state.essay_prompt

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            result_df.to_excel(writer, index=False, sheet_name='批改结果')
        
        st.sidebar.download_button(
            label="✅ 点击下载Excel文件",
            data=output.getvalue(),
            file_name="作文批改结果.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.sidebar.success("导出文件已生成！")
    