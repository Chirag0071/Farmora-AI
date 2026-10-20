import streamlit as st


st.markdown(
    """
    <div class="glass-card">

    <h1>❓ Help</h1>

    <h2>🚀 Quick start</h2>
    <ol>
        <li><b>Home</b> – click <b>Predict Now</b> (or open <b>Predict</b> from the sidebar).</li>
        <li><b>Select State</b> – choose your state from the dropdown.</li>
        <li><b>Select District</b> – pick your district. If the list does not load, type the district name instead.</li>
        <li><b>Select Crop</b> – choose the crop you want to analyse.</li>
        <li><b>Production Cost (₹/qtl)</b> – enter your approximate cost to produce one quintal (100 kg).</li>
        <li><b>Historical Arrival Date</b> <i>(optional)</i> – choose a date to see what each mandi paid on that day.</li>
        <li>Click <b>Show Details</b> to open the results.</li>
    </ol>

    <h2>📊 Reading the results</h2>
    <ul>
        <li><b>Current Mandi Price</b> – the latest price found for your crop:
            <i>Min</i> and <i>Max</i> are the lowest and highest sale prices, <i>Modal</i> is the most common one.
            All prices are in ₹ per quintal.</li>
        <li><b>Prices on selected date</b> – a table of market, variety, grade and prices for that day.
            If no mandi reported that day, the latest available date is mentioned instead.</li>
        <li><b>Past, Present &amp; Future Price</b> – stacked columns:
            <span style="color:#4da3ff"><b>blue</b></span> = past monthly averages,
            <span style="color:#ffb703"><b>amber</b></span> = latest observed price,
            <span style="color:#2ecc71"><b>green</b></span> = 12‑month estimate. Hover a column for the exact value.</li>
        <li><b>Mandi Locations</b> – every mandi reporting in your district. Hover over a red dot to see the market name; drag to pan and scroll to zoom.</li>
        <li><b>Estimated Profit / Loss</b> – average forecast price minus your production cost. Positive means an estimated margin, negative an estimated loss, per quintal.</li>
        <li><b>Crop Suggestions</b> – click <b>View Crop Suggestions</b> to see other crops in your district ranked by market activity.</li>
    </ul>

    <h2>🛠️ Troubleshooting</h2>
    <ul>
        <li><b>"Couldn't reach the FastAPI backend"</b> – the backend is not running. Start it with
            <code>uvicorn backend.main:app --port 8000</code>.</li>
        <li><b>"AGMARKNET_API_KEY is missing"</b> – add your data.gov.in key to the <code>.env</code> file and restart the backend.</li>
        <li><b>"No price data found"</b> – the crop may not be traded in that district, or is listed under a different name. Try another crop or a nearby district.</li>
        <li><b>No record for my date</b> – mandis do not report every day, and today's prices appear only after upload. Try a nearby date.</li>
        <li><b>The map takes long to appear</b> – the first lookup for a district locates each market one by one (about one per second). Later visits are fast because results are saved.</li>
        <li><b>Some markets are missing on the map</b> – small mandis can't always be found by name and are skipped rather than shown in the wrong place.</li>
        <li><b>API timeout</b> – the government API is sometimes slow. Wait a moment and try again; saved data is used when it is unavailable.</li>
    </ul>

    <h2>💡 Tips</h2>
    <ul>
        <li>Enter a realistic production cost – it directly drives the profit/loss estimate.</li>
        <li>Forecasts are estimates from past trends, not guarantees. Compare with local mandi rates before you decide.</li>
        <li>All fields marked as required must be filled before <b>Show Details</b> works; a warning tells you what is missing.</li>
    </ul>

    </div>
    """,
    unsafe_allow_html=True
)