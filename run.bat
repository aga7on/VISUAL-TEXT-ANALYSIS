@echo off
call .venv\Scripts\activate.bat
pip install streamlit requests aiohttp jinja2 duckduckgo-search Pillow beautifulsoup4 playwright
streamlit run app.py
