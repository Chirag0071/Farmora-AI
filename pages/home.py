import streamlit as st


st.markdown(
    """
    <div class="hero">
    <h1>
    Farmora 🌾 : Smart Crop Suggestion<br>
            System
        </h1>
    <p>Forecasting Harvests, Empowering Indian Farmers
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# Predict Now button
col1, col2, col3 = st.columns([4, 2, 4])

with col2:

    if st.button(
        "Predict Now",
        type="primary",
        use_container_width=True
    ):
        st.switch_page("pages/predict.py")