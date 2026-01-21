import streamlit as st
import anthropic
import requests
import base64
from datetime import datetime
import time
import json

# Page configuration
st.set_page_config(
    page_title="SEO Competitive Analyst",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state
if 'analysis_history' not in st.session_state:
    st.session_state.analysis_history = []

# SEO Agent System Prompt
SEO_ANALYST_PROMPT = """You are an expert SEO competitive analyst specializing in ranking strategies.

Your role:
- Analyze SERP positioning data and competitive landscapes
- Identify specific ranking gaps and opportunities
- Evaluate competitor strengths across content, backlinks, and technical factors
- Develop prioritized, actionable game plans to overtake competitor rankings
- Recommend tactics with estimated impact and effort levels

Always provide:
- Data-driven insights with specific metrics
- Prioritized recommendations (High/Medium/Low impact)
- Specific action items (content improvements, link building targets, technical fixes)
- Success metrics and timelines
- Competitor weakness analysis

Format your strategic recommendations clearly with priority levels and expected outcomes."""

DATAFORSEO_BASE_URL = "https://api.dataforseo.com/v3"


def dataforseo_request(login, password, endpoint, method="POST", data=None):
    """Make request to DataForSEO API"""
    creds = f"{login}:{password}"
    encoded_creds = base64.b64encode(creds.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_creds}",
        "Content-Type": "application/json"
    }
    
    url = f"{DATAFORSEO_BASE_URL}/{endpoint}"
    
    try:
        if method == "POST":
            response = requests.post(url, json=data, headers=headers)
        else:
            response = requests.get(url, headers=headers)
        
        response.raise_for_status()
        result = response.json()
        
        if result.get('status_code') == 20000:
            return result
        else:
            st.error(f"API Error: {result.get('status_message')}")
            return None
            
    except requests.exceptions.RequestException as e:
        st.error(f"Request Error: {e}")
        return None


def get_serp_live(login, password, keyword, location="United States"):
    """Get live SERP results"""
    endpoint = "serp/google/organic/live/advanced"
    data = [{
        "keyword": keyword,
        "location_name": location,
        "language_name": "English",
        "device": "desktop",
        "depth": 10
    }]
    return dataforseo_request(login, password, endpoint, "POST", data)


def get_backlinks_summary(login, password, target):
    """Get backlink summary"""
    endpoint = "backlinks/summary/live"
    data = [{"target": target, "mode": "domain"}]
    return dataforseo_request(login, password, endpoint, "POST", data)


def get_keyword_difficulty(login, password, keywords):
    """Get keyword difficulty"""
    endpoint = "dataforseo_labs/google/bulk_keyword_difficulty/live"
    data = [{
        "keywords": [keywords] if isinstance(keywords, str) else keywords,
        "location_code": 2840,
        "language_code": "en"
    }]
    return dataforseo_request(login, password, endpoint, "POST", data)


def analyze_competitor_landscape(login, password, keyword, your_domain, location):
    """Fetch and analyze competitive data"""
    
    progress_bar = st.progress(0)
    status = st.empty()
    
    # Get SERP data
    status.text("🔍 Fetching SERP rankings...")
    progress_bar.progress(20)
    serp_result = get_serp_live(login, password, keyword, location)
    
    if not serp_result or not serp_result.get('tasks'):
        return None
    
    task = serp_result['tasks'][0]
    if task['status_code'] != 20000:
        st.error(f"SERP Error: {task['status_message']}")
        return None
    
    serp_items = task['result'][0]['items'] if task['result'] else []
    
    # Parse SERP results
    your_position = None
    your_url = None
    competitors = []
    
    for item in serp_items:
        if item.get('type') != 'organic':
            continue
        
        domain = item.get('domain', '')
        url = item.get('url', '')
        position = item.get('rank_absolute', 0)
        
        if your_domain.lower() in domain.lower():
            your_position = position
            your_url = url
        else:
            competitors.append({
                'position': position,
                'domain': domain,
                'url': url,
                'title': item.get('title', 'N/A'),
                'description': item.get('description', 'N/A')
            })
    
    if not your_position:
        your_position = "Not in top 10"
    
    progress_bar.progress(40)
    
    # Get keyword metrics
    status.text("📊 Analyzing keyword difficulty...")
    kw_difficulty = get_keyword_difficulty(login, password, keyword)
    kw_metrics = {}
    if kw_difficulty and kw_difficulty['tasks'][0]['result']:
        kw_data = kw_difficulty['tasks'][0]['result'][0]['items'][0]
        kw_metrics = {
            'keyword_difficulty': kw_data.get('keyword_difficulty'),
            'search_volume': kw_data.get('keyword_info', {}).get('search_volume'),
            'cpc': kw_data.get('keyword_info', {}).get('cpc')
        }
    
    progress_bar.progress(60)
    
    # Get your backlinks
    status.text(f"🔗 Analyzing backlinks for {your_domain}...")
    your_backlinks = get_backlinks_summary(login, password, your_domain)
    your_bl_data = {}
    if your_backlinks and your_backlinks['tasks'][0]['result']:
        bl = your_backlinks['tasks'][0]['result'][0]
        your_bl_data = {
            'backlinks': bl.get('backlinks', 0),
            'referring_domains': bl.get('referring_domains', 0),
            'rank': bl.get('rank', 0)
        }
    
    progress_bar.progress(70)
    
    # Get competitor backlinks (top 3)
    status.text("🔗 Analyzing competitor backlinks...")
    for idx, comp in enumerate(competitors[:3], 1):
        comp_bl = get_backlinks_summary(login, password, comp['domain'])
        if comp_bl and comp_bl['tasks'][0]['result']:
            bl = comp_bl['tasks'][0]['result'][0]
            comp['backlink_data'] = {
                'backlinks': bl.get('backlinks', 0),
                'referring_domains': bl.get('referring_domains', 0),
                'rank': bl.get('rank', 0)
            }
        else:
            comp['backlink_data'] = {}
        progress_bar.progress(70 + (idx * 10))
        time.sleep(0.5)
    
    progress_bar.progress(100)
    status.text("✅ Data collection complete!")
    time.sleep(0.5)
    status.empty()
    progress_bar.empty()
    
    return {
        'keyword': keyword,
        'keyword_metrics': kw_metrics,
        'my_position': your_position,
        'my_domain': your_domain,
        'my_url': your_url,
        'my_backlinks': your_bl_data,
        'competitors': competitors[:5]
    }


def analyze_with_claude(api_key, keyword_data, timeline):
    """Get strategic analysis from Claude"""
    
    client = anthropic.Anthropic(api_key=api_key)
    
    kw_metrics = keyword_data.get('keyword_metrics', {})
    my_bl = keyword_data.get('my_backlinks', {})
    
    prompt = f"""Analyze this competitive landscape for the keyword: "{keyword_data['keyword']}"

KEYWORD METRICS:
- Search Volume: {kw_metrics.get('search_volume', 'N/A'):,} searches/month
- Keyword Difficulty: {kw_metrics.get('keyword_difficulty', 'N/A')}/100
- CPC: ${kw_metrics.get('cpc', 'N/A')}

MY SITE ({keyword_data['my_domain']}):
- Current Position: #{keyword_data['my_position']}
- URL: {keyword_data.get('my_url', 'N/A')}
- Total Backlinks: {my_bl.get('backlinks', 'N/A'):,}
- Referring Domains: {my_bl.get('referring_domains', 'N/A'):,}
- Domain Rank: {my_bl.get('rank', 'N/A')}

TOP COMPETITORS:
"""
    
    for comp in keyword_data['competitors']:
        bl_data = comp.get('backlink_data', {})
        prompt += f"""
Position #{comp['position']} - {comp['domain']}
- URL: {comp.get('url', 'N/A')}
- Title: {comp.get('title', 'N/A')}
- Total Backlinks: {bl_data.get('backlinks', 'N/A'):,}
- Referring Domains: {bl_data.get('referring_domains', 'N/A'):,}
- Domain Rank: {bl_data.get('rank', 'N/A')}
"""
    
    prompt += f"""

TASK:
Provide a comprehensive strategic plan to move from position #{keyword_data['my_position']} to top 3 within {timeline}.

Provide:
1. **SERP Analysis**: What patterns in top results? What intent?
2. **Backlink Gap**: How significant is the deficit?
3. **Prioritized Action Plan**: Specific tactics with effort/impact levels
4. **Success Metrics**: How to measure progress

Be specific and actionable."""

    with st.spinner("🤖 Claude is analyzing the competitive landscape..."):
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=SEO_ANALYST_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
    
    return message.content[0].text


# Main UI
st.title("🔍 SEO Competitive Analyst")
st.markdown("Analyze your keyword rankings and get AI-powered strategic recommendations")

# Sidebar for settings
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # API credentials
    st.subheader("API Credentials")
    dataforseo_login = st.text_input("DataForSEO Login", type="password")
    dataforseo_password = st.text_input("DataForSEO Password", type="password")
    anthropic_key = st.text_input("Anthropic API Key", type="password")
    
    st.markdown("---")
    st.markdown("**Don't have API keys?**")
    st.markdown("- [DataForSEO](https://app.dataforseo.com/api-access)")
    st.markdown("- [Anthropic](https://console.anthropic.com)")
    
    st.markdown("---")
    st.subheader("📊 Analysis History")
    if st.session_state.analysis_history:
        for idx, item in enumerate(reversed(st.session_state.analysis_history[-5:])):
            if st.button(f"{item['keyword'][:30]}...", key=f"history_{idx}"):
                st.session_state.current_analysis = item

# Main content area
tab1, tab2 = st.tabs(["🎯 New Analysis", "📈 Results"])

with tab1:
    st.header("Keyword Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        your_domain = st.text_input("Your Domain", placeholder="example.com")
        keyword = st.text_input("Target Keyword", placeholder="best project management software")
    
    with col2:
        location = st.selectbox("Location", ["United States", "United Kingdom", "Canada", "Australia"])
        timeline = st.selectbox("Target Timeline", ["3 months", "6 months", "9 months", "12 months"])
    
    analyze_btn = st.button("🚀 Analyze Keyword", type="primary", use_container_width=True)
    
    if analyze_btn:
        if not all([dataforseo_login, dataforseo_password, anthropic_key, your_domain, keyword]):
            st.error("⚠️ Please fill in all fields and API credentials")
        else:
            # Fetch competitive data
            landscape_data = analyze_competitor_landscape(
                dataforseo_login, dataforseo_password, keyword, your_domain, location
            )
            
            if landscape_data:
                # Get Claude's analysis
                analysis = analyze_with_claude(anthropic_key, landscape_data, timeline)
                
                # Save to history
                result = {
                    'keyword': keyword,
                    'domain': your_domain,
                    'timestamp': datetime.now().isoformat(),
                    'data': landscape_data,
                    'analysis': analysis
                }
                st.session_state.analysis_history.append(result)
                st.session_state.current_analysis = result
                
                st.success("✅ Analysis complete! Check the Results tab.")
                st.rerun()

with tab2:
    if 'current_analysis' in st.session_state:
        result = st.session_state.current_analysis
        data = result['data']
        
        # Header with key metrics
        st.header(f"📊 Analysis: {result['keyword']}")
        st.caption(f"Domain: {result['domain']} | {datetime.fromisoformat(result['timestamp']).strftime('%Y-%m-%d %H:%M')}")
        
        # Key metrics in columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            position = data.get('my_position', 'N/A')
            st.metric("Current Position", f"#{position}" if isinstance(position, int) else position)
        
        with col2:
            sv = data.get('keyword_metrics', {}).get('search_volume', 0)
            st.metric("Search Volume", f"{sv:,}" if sv else "N/A")
        
        with col3:
            kd = data.get('keyword_metrics', {}).get('keyword_difficulty', 0)
            st.metric("Keyword Difficulty", f"{kd}/100" if kd else "N/A")
        
        with col4:
            bl = data.get('my_backlinks', {}).get('backlinks', 0)
            st.metric("Your Backlinks", f"{bl:,}" if bl else "N/A")
        
        st.markdown("---")
        
        # Competitor comparison table
        st.subheader("🏆 Top Competitors")
        
        competitors = data.get('competitors', [])[:5]
        if competitors:
            comp_data = []
            for comp in competitors:
                bl_data = comp.get('backlink_data', {})
                comp_data.append({
                    'Position': f"#{comp['position']}",
                    'Domain': comp['domain'],
                    'Backlinks': f"{bl_data.get('backlinks', 0):,}",
                    'Ref Domains': f"{bl_data.get('referring_domains', 0):,}",
                    'Title': comp.get('title', 'N/A')[:60] + "..."
                })
            
            st.dataframe(comp_data, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # Strategic analysis
        st.subheader("🎯 Strategic Recommendations")
        st.markdown(result['analysis'])
        
        # Download button
        report_text = f"""SEO COMPETITIVE ANALYSIS REPORT
{'='*80}
Keyword: {result['keyword']}
Domain: {result['domain']}
Date: {datetime.fromisoformat(result['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}
{'='*80}

CURRENT METRICS:
- Position: #{data.get('my_position')}
- Search Volume: {data.get('keyword_metrics', {}).get('search_volume', 'N/A')}
- Keyword Difficulty: {data.get('keyword_metrics', {}).get('keyword_difficulty', 'N/A')}

{'='*80}
STRATEGIC ANALYSIS
{'='*80}

{result['analysis']}
"""
        
        st.download_button(
            "📥 Download Report",
            report_text,
            file_name=f"seo_analysis_{result['keyword'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
    else:
        st.info("👈 Run an analysis to see results here")

# Footer
st.markdown("---")
st.caption("Built with Claude & DataForSEO | 🔍 Analyze smarter, rank higher")
