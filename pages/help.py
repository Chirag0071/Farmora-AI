import streamlit as st


st.markdown(
"""
<div style="color: white; text-shadow: 0 2px 8px rgba(0,0,0,0.7); max-width: 900px; margin: 70px auto; padding: 30px;">

<h1>❓ Help</h1>

<h2>How to use Farmora?</h2>

<p>
<b>1. Home</b><br>
Start from the Home page and learn about Farmora.
</p>

<p>
<b>2. Predict</b><br>
Select your state, enter your district and select
the crop you want to analyze.
</p>

<p>
<b>3. Production Cost</b><br>
Enter the approximate production cost per quintal.
</p>

<p>
<b>4. Show Details</b><br>
Click the Show Details button to view the submitted
information.
</p>

<h2>🔄 Working Process</h2>

<p>
<b>Step 1 — Choose your state:</b> Pick your state
from the dropdown so Farmora knows the region your
details belong to.
</p>

<p>
<b>Step 2 — Enter your district:</b> Type in the
district name so your entry is specific to your
local area.
</p>

<p>
<b>Step 3 — Select your crop:</b> Choose the crop
you want to analyze from the crop dropdown.
</p>

<p>
<b>Step 4 — Enter production cost:</b> Provide your
estimated production cost per quintal (₹/qtl).
</p>

<p>
<b>Step 5 — Submit:</b> Click <b>Show Details</b>.
Farmora checks that the state, district, and crop
fields are all filled in — if something is missing,
a warning tells you what to complete.
</p>

<p>
<b>Step 6 — Review your summary:</b> Once
everything is filled in, Farmora confirms the
submission and displays your state, district, crop,
and formatted production cost back to you.
</p>

<h2>⚠️ Important</h2>

<p>
Make sure all required fields are filled before
submitting your prediction.
</p>

</div>
""",
unsafe_allow_html=True
)