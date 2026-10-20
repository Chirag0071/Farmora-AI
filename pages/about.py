import streamlit as st


st.markdown(
    """
    <div class="glass-card">

    <h1>ℹ️ About Farmora</h1>

    <p>
    Farmora is a Smart Crop Price &amp; Suggestion System for Indian farmers.
    It turns public mandi price data into simple, visual insights so farmers can
    judge when and where their crop is likely to sell well.
    </p>

    <h2>🎯 Objective</h2>
    <p>
    Give farmers a clear picture of current mandi prices, recent price trends,
    an estimated price outlook and nearby markets, so that selling and planting
    decisions are backed by data.
    </p>

    <h2>✨ What Farmora does</h2>
    <ul>
        <li>Shows the latest <b>min, modal and max mandi prices</b> for your crop and district.</li>
        <li>Looks up prices for a <b>chosen past date</b>, market by market.</li>
        <li>Plots <b>past, present and future prices</b> in one stacked column chart.</li>
        <li>Estimates <b>profit or loss per quintal</b> against your production cost.</li>
        <li>Maps <b>every mandi in the district</b> – hover a red dot to see its name.</li>
        <li>Suggests <b>other crops showing strong market activity</b> in your district.</li>
    </ul>

    <h2>🔄 How it works</h2>
    <ol>
        <li>You enter state, district, crop and production cost.</li>
        <li>The FastAPI backend fetches daily prices from the <b>AGMARKNET</b> API on data.gov.in
            (live daily prices plus a historical archive) and saves a local copy.</li>
        <li>Prices are cleaned and averaged per month.</li>
        <li>A <b>damped linear trend</b> over the latest 12 months gives the 12‑month estimate.
            This is a simple statistical baseline, not a trained machine‑learning model.</li>
        <li>Market names are located with OpenStreetMap and shown on the map.</li>
        <li>Crops in the district are scored on observations, number of markets, average price and recent trend.</li>
    </ol>

    <h2>🛠️ Technologies</h2>
    <p>
    Python 3.11 • Streamlit • FastAPI • Uvicorn • Pandas • NumPy • Plotly • pydeck •
    AGMARKNET (data.gov.in) • OpenStreetMap Nominatim
    </p>

    <h2>⚠️ Limitations &amp; disclaimer</h2>
    <ul>
        <li>Forecasts are estimates from past prices only – no weather, seasonality or policy data.</li>
        <li>The public API may return limited records, so some crops or districts have sparse data.</li>
        <li>Crop suggestions reflect market activity, not soil suitability or agronomic advice.</li>
        <li>Farmora is not financial advice. Always confirm prices with your local mandi.</li>
    </ul>

    <h2>👨‍💻 Developer</h2>
    <p>
    Built by <b>Chirag</b> –
    <a href="https://github.com/Chirag0071" style="color:#ffb703">github.com/Chirag0071</a><br>
    Licensed under the MIT License.
    </p>

    </div>
    """,
    unsafe_allow_html=True
)