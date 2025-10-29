"""Extract detailed info from CVs"""
from read_cv4 import extract_text_from_pdf, extract_key_info

cvs = ['Thien-CV.pdf', 'LyMinh-CV.pdf', 'Thanh-CV.pdf', 'Mai-CV.pdf']

for cv_file in cvs:
    print(f"\n{'='*80}")
    print(f"📄 {cv_file}")
    print('='*80)
    
    text = extract_text_from_pdf(cv_file)
    info = extract_key_info(text)
    
    print(f"\n📧 Email: {info.get('email', 'N/A')}")
    print(f"📱 Phone: {info.get('phone', 'N/A')}")
    print(f"🎓 GPA: {info.get('gpa', 'N/A')}")
    
    print(f"\n🎓 EDUCATION ({len(info.get('education', ''))} chars):")
    print(info.get('education', 'N/A')[:500])
    
    print(f"\n💼 EXPERIENCE ({len(info.get('experience', ''))} chars):")
    print(info.get('experience', 'N/A')[:500])
    
    print(f"\n🚀 PROJECTS ({len(info.get('projects', ''))} chars):")
    print(info.get('projects', 'N/A')[:800])
    
    print(f"\n💻 SKILLS ({len(info.get('skills', ''))} chars):")
    print(info.get('skills', 'N/A')[:300])
    
    print(f"\n🏆 CERTIFICATES ({len(info.get('certificates', ''))} chars):")
    print(info.get('certificates', 'N/A')[:400])
    
    activities = info.get('activities', '') or ''
    print(f"\n🎯 ACTIVITIES ({len(activities)} chars):")
    print(activities[:400] if activities else 'N/A')
    
    print(f"\n🔗 LINKS: {len(info.get('links', []))} links")
    for link in info.get('links', []):
        print(f"   - {link}")
