"""
THE BRAIN - Hệ thống AI phân tích và chấm điểm CV
Train từ dữ liệu Sheet1 & Sheet2, sau đó predict cho CV mới từ read_cv4
"""

import os
import sys
import glob
import pickle
import re
import argparse
from pathlib import Path
from datetime import datetime
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestRegressor
import warnings
warnings.filterwarnings('ignore')

try:
    import xgboost as xgb
    USE_XGBOOST = True
except ImportError:
    USE_XGBOOST = False
    print("⚠️ XGBoost không có, sẽ dùng Random Forest")

# Import các hàm từ read_cv4
try:
    from read_cv4 import extract_text_from_pdf, extract_key_info
    import config
except ImportError as e:
    print(f"❌ Lỗi: Không thể import từ read_cv4.py: {e}")
    sys.exit(1)


# ============================================================================
# HELPER FUNCTIONS - Parse date, detect student status, etc.
# ============================================================================

def parse_date_flexible(date_str):
    """
    Parse nhiều định dạng ngày tháng từ CV
    VD: "10/2022", "06/2023", "nay", "hiện tại", "27/05/2024", "2023-2024", "2019-now"

    Returns: datetime object hoặc None
    """
    if pd.isna(date_str):
        return None

    date_str = str(date_str).strip().lower()

    # Current date indicators
    if any(word in date_str for word in ['nay', 'hiện tại', 'present', 'current', 'now']):
        return datetime.now()

    # Try multiple formats
    patterns = [
        r'(\d{1,2})/(\d{4})',  # MM/YYYY or M/YYYY
        r'(\d{1,2})-(\d{4})',  # MM-YYYY
        r'(\d{1,2})/(\d{1,2})/(\d{4})',  # DD/MM/YYYY
        r'(\d{4})',  # Just year
    ]

    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 1:  # Just year
                    return datetime(int(groups[0]), 1, 1)
                elif len(groups) == 2:  # Month/Year
                    return datetime(int(groups[1]), int(groups[0]), 1)
                elif len(groups) == 3:  # Day/Month/Year
                    return datetime(int(groups[2]), int(groups[1]), int(groups[0]))
            except:
                continue

    # Fallback: try dateutil parser
    try:
        return date_parser.parse(date_str, dayfirst=True)
    except:
        return None


def calculate_months_between(start_date, end_date):
    """Tính số tháng giữa 2 ngày"""
    if start_date is None or end_date is None:
        return 0

    try:
        delta = relativedelta(end_date, start_date)
        return delta.years * 12 + delta.months
    except:
        return 0


def detect_student_status(cv_data):
    """
    Phát hiện tình trạng: Student (đang học) vs Graduated (đã tốt nghiệp)

    Returns: 'Student', 'Graduated', hoặc 'Unknown'
    """
    education = str(cv_data.get('education', '')).lower()
    objective = str(cv_data.get('objective', '')).lower()
    job_title = str(cv_data.get('job_title', '')).lower()

    # Keywords for students
    student_keywords = [
        'thực tập sinh', 'intern', 'đang học', 'sinh viên',
        'năm 2', 'năm 3', 'năm 4', 'year 2', 'year 3', 'year 4',
        'expected graduation', 'dự kiến tốt nghiệp'
    ]

    # Keywords for graduated
    graduated_keywords = [
        'tốt nghiệp', 'graduated', 'bachelor', 'master', 'phd',
        'đã tốt nghiệp', 'bằng cử nhân', 'bằng thạc sĩ'
    ]

    # Check graduation year
    current_year = datetime.now().year
    graduation_year = cv_data.get('graduation_year')
    if graduation_year:
        try:
            grad_year = int(graduation_year)
            if grad_year <= current_year:
                return 'Graduated'
            else:
                return 'Student'
        except:
            pass

    # Check education text for date ranges like "2023 - now" or "2019-2023"
    edu_year_match = re.search(r'(\d{4})\s*-\s*(now|nay|hiện tại|\d{4})', education)
    if edu_year_match:
        end_year = edu_year_match.group(2)
        if end_year in ['now', 'nay', 'hiện tại']:
            return 'Student'
        try:
            if int(end_year) <= current_year:
                return 'Graduated'
            else:
                return 'Student'
        except:
            pass

    # Check keywords
    all_text = f"{education} {objective} {job_title}"

    if any(kw in all_text for kw in student_keywords):
        return 'Student'

    if any(kw in all_text for kw in graduated_keywords):
        return 'Graduated'

    return 'Unknown'


class CVScoringRules:
    """Hệ thống rules để tạo điểm tự động cho CV"""
    
    # Định nghĩa keywords cho từng ngành nghề (15 ngành)
    INDUSTRY_KEYWORDS = {
        'IT/Software': ['developer', 'engineer', 'programmer', 'software', 'web', 'mobile', 'backend', 'frontend', 
                       'fullstack', 'devops', 'java', 'python', 'javascript', 'react', 'node', 'docker', 'kubernetes',
                       'aws', 'cloud', 'database', 'api', 'git', 'agile', 'scrum', 'coding', 'programming'],
        'Data/AI': ['data', 'analytics', 'machine learning', 'deep learning', 'ai', 'ml', 'tensorflow', 'pytorch',
                   'data science', 'data engineer', 'data analyst', 'big data', 'spark', 'hadoop', 'sql', 'python',
                   'statistics', 'modeling', 'kaggle', 'nlp', 'computer vision'],
        'Design': ['design', 'ui', 'ux', 'figma', 'sketch', 'photoshop', 'illustrator', 'graphic', 'visual',
                  'wireframe', 'prototype', 'user experience', 'user interface', 'typography', 'branding'],
        'Marketing': ['marketing', 'seo', 'sem', 'google ads', 'facebook ads', 'social media', 'content',
                     'campaign', 'branding', 'email marketing', 'digital marketing', 'roi', 'conversion',
                     'analytics', 'hubspot', 'growth', 'acquisition'],
        'Sales': ['sales', 'business development', 'account', 'revenue', 'quota', 'deal', 'client',
                 'customer', 'relationship', 'negotiation', 'presentation', 'crm', 'salesforce', 'b2b',
                 'enterprise', 'pipeline', 'closing'],
        'HR': ['hr', 'human resources', 'recruitment', 'talent', 'hiring', 'employee', 'engagement',
              'compensation', 'benefits', 'culture', 'retention', 'onboarding', 'performance management',
              'hris', 'payroll', 'labor law'],
        'Finance': ['finance', 'financial', 'accounting', 'budget', 'forecasting', 'analysis', 'excel',
                   'modeling', 'investment', 'valuation', 'fp&a', 'reporting', 'audit', 'tax', 'cfa',
                   'gaap', 'balance sheet', 'p&l'],
        'QA/Testing': ['qa', 'quality', 'testing', 'test', 'automation', 'selenium', 'cypress', 'jira',
                      'bug', 'defect', 'manual testing', 'api testing', 'performance testing'],
        'Product': ['product', 'roadmap', 'strategy', 'backlog', 'stakeholder', 'okr', 'kpi', 'mvp',
                   'user story', 'feature', 'launch', 'product owner', 'product manager'],
        'Security': ['security', 'cybersecurity', 'penetration', 'ethical hacking', 'vulnerability',
                    'owasp', 'kali linux', 'burp suite', 'firewall', 'encryption', 'compliance'],
        # 5 NGÀNH MỚI (BỔ SUNG)
        'Content': ['content', 'writer', 'copywriter', 'blogger', 'journalist', 'editor', 'seo',
                   'blog', 'article', 'writing', 'storytelling', 'social media', 'video', 'youtube',
                   'tiktok', 'instagram', 'facebook', 'copywriting', 'creative writing'],
        'Customer Service': ['customer service', 'customer support', 'support', 'helpdesk', 'call center',
                            'customer care', 'technical support', 'service desk', 'zendesk', 'intercom',
                            'freshdesk', 'client service', 'customer satisfaction', 'csat', 'nps'],
        'Operations': ['operations', 'logistics', 'supply chain', 'warehouse', 'procurement', 'inventory',
                      'lean', 'six sigma', 'process improvement', 'operations manager', 'supply',
                      'erp', 'sap', 'wms', 'distribution', 'fulfillment'],
        'Legal': ['legal', 'lawyer', 'attorney', 'counsel', 'compliance', 'law', 'contract', 'litigation',
                 'corporate law', 'intellectual property', 'legal advisor', 'paralegal', 'bar exam',
                 'regulation', 'legal research'],
        'Healthcare': ['healthcare', 'medical', 'doctor', 'physician', 'nurse', 'nursing', 'clinical',
                      'patient care', 'hospital', 'health', 'medicine', 'registered nurse', 'rn', 'md',
                      'pharmacist', 'dentist', 'therapy', 'medical license'],
    }

    @staticmethod
    def detect_industry(cv_data):
        """Phát hiện ngành nghề từ CV"""
        # Ghép tất cả text fields
        text_fields = [
            str(cv_data.get('objective', '')),
            str(cv_data.get('job_description', '')),
            str(cv_data.get('job_title', '')),
            str(cv_data.get('project_description', '')),
            str(cv_data.get('skills_list', '')),
            str(cv_data.get('major', '')),
        ]
        full_text = ' '.join(text_fields).lower()
        
        # Đếm keywords cho mỗi ngành
        industry_scores = {}
        for industry, keywords in CVScoringRules.INDUSTRY_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in full_text)
            industry_scores[industry] = score
        
        # Lấy ngành có điểm cao nhất
        if max(industry_scores.values()) > 0:
            detected_industry = max(industry_scores, key=industry_scores.get)
            return detected_industry, industry_scores[detected_industry]
        
        return 'General', 0

    @staticmethod
    def detect_seniority(cv_data):
        """Phát hiện seniority level từ CV (Entry, Mid, Senior, Lead)"""
        # Tính năm kinh nghiệm
        exp_text = str(cv_data.get('job_description', ''))
        
        # Tìm keywords về seniority (thêm Lead)
        lead_keywords = ['lead', 'principal', 'staff engineer', 'chief', 'head of', 'director', 
                        'vp', 'vice president', 'architect']
        senior_keywords = ['senior', 'sr.', 'sr ', 'tech lead', 'team lead']
        mid_keywords = ['specialist', 'engineer', 'developer', 'analyst', 'consultant']
        entry_keywords = ['intern', 'junior', 'trainee', 'fresher', 'graduate', 'entry', 'jr.', 'jr ']
        
        exp_lower = exp_text.lower()
        title_lower = str(cv_data.get('job_title', '')).lower()
        
        # Check title first (ưu tiên từ cao xuống thấp)
        # Lead level (cao nhất)
        if any(keyword in title_lower for keyword in lead_keywords):
            # Nếu có "senior lead" hay "lead" mà không có "senior" ở trước
            if 'principal' in title_lower or 'staff' in title_lower or 'chief' in title_lower:
                return 'Lead'
            if 'head of' in title_lower or 'director' in title_lower:
                return 'Lead'
            if 'lead' in title_lower and 'senior' not in title_lower:
                return 'Lead'
        
        # Senior level
        if any(keyword in title_lower for keyword in senior_keywords):
            return 'Senior'
        
        # Entry level
        if any(keyword in entry_keywords for keyword in entry_keywords):
            return 'Entry'
            
        # Check experience text
        lead_count = sum(1 for k in lead_keywords if k in exp_lower)
        senior_count = sum(1 for k in senior_keywords if k in exp_lower)
        entry_count = sum(1 for k in entry_keywords if k in exp_lower)
        
        if lead_count >= 3:
            return 'Lead'
        elif senior_count >= 2:
            return 'Senior'
        elif entry_count >= 1:
            return 'Entry'
        else:
            return 'Mid'
    
    @staticmethod
    def detect_quantified_achievements(cv_data):
        """Phát hiện achievements được định lượng (numbers, %, $)"""
        text_fields = [
            str(cv_data.get('job_description', '')),
            str(cv_data.get('project_description', '')),
        ]
        full_text = ' '.join(text_fields)
        
        # Pattern cho numbers với impact keywords
        import re
        achievement_patterns = [
            r'\d+%',  # "150%", "20%"
            r'\$\d+[KMB]?',  # "$200K", "$5M"
            r'\d+[KM]?\+?\s*(users|customers|clients|employees)',  # "10M+ users"
            r'(increased|improved|reduced|grew|boosted|optimized)\s+\w+\s+by\s+\d+',  # "increased sales by 150"
            r'\d+x\s+(faster|better|more)',  # "2x faster"
        ]
        
        score = 0
        for pattern in achievement_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            score += len(matches)
        
        return min(score, 10)  # Cap at 10

    @staticmethod
    def score_gpa(gpa, seniority='Mid'):
        """Chấm điểm GPA: 0-10 điểm, adjust theo seniority"""
        if pd.isna(gpa):
            return 5  # Điểm trung bình nếu không có GPA

        try:
            gpa_val = float(gpa)
            # Chuẩn hóa về thang 10
            if gpa_val <= 4.0:
                gpa_val = gpa_val * 2.5  # Chuyển từ thang 4 sang thang 10

            # Base score
            if gpa_val >= 9.0:
                base_score = 10
            elif gpa_val >= 8.5:
                base_score = 9
            elif gpa_val >= 8.0:
                base_score = 8
            elif gpa_val >= 7.5:
                base_score = 7
            elif gpa_val >= 7.0:
                base_score = 6
            elif gpa_val >= 6.5:
                base_score = 5
            elif gpa_val >= 6.0:
                base_score = 4
            else:
                base_score = 3
            
            # Adjust by seniority (GPA matters less for senior roles)
            if seniority == 'Lead':
                return base_score * 0.5  # Giảm 50% cho Lead (GPA gần như không quan trọng)
            elif seniority == 'Senior':
                return base_score * 0.7  # Reduce importance
            elif seniority == 'Entry':
                return base_score * 1.2  # Increase importance (cap at 10)
            
            return min(base_score, 10)
        except:
            return 5

    @staticmethod
    def score_education(education_level):
        """Chấm điểm trình độ: 0-10 điểm"""
        if pd.isna(education_level):
            return 5

        edu = str(education_level).lower()
        if 'tiến sĩ' in edu or 'phd' in edu or 'doctor' in edu:
            return 10
        elif 'thạc sĩ' in edu or 'master' in edu:
            return 9
        elif 'đại học' in edu or 'university' in edu or 'bachelor' in edu:
            return 7
        elif 'cao đẳng' in edu or 'college' in edu:
            return 5
        else:
            return 3

    @staticmethod
    def score_experience(job_description, start_date, end_date):
        """
        Chấm điểm kinh nghiệm: 0-30 điểm
        - Thời gian làm việc thực tế (parse date chính xác): 0-15 điểm
        - Chất lượng mô tả: 0-15 điểm
        """
        score = 0

        # 1. Điểm cho thời gian làm việc THỰC TẾ (parse chính xác)
        start = parse_date_flexible(start_date)
        end = parse_date_flexible(end_date)

        if start and end:
            months = calculate_months_between(start, end)

            # Thang điểm theo thời gian (thị trường thực tế)
            if months >= 36:  # 3+ năm
                score += 15
            elif months >= 24:  # 2-3 năm
                score += 13
            elif months >= 12:  # 1-2 năm
                score += 10
            elif months >= 6:  # 6-12 tháng
                score += 7
            elif months >= 3:  # 3-6 tháng
                score += 4
            else:  # < 3 tháng
                score += 2

        # 2. Điểm cho chất lượng mô tả kinh nghiệm
        if not pd.isna(job_description) and len(str(job_description).strip()) > 0:
            desc = str(job_description).lower()
            desc_len = len(desc)

            # Base score cho có kinh nghiệm
            score += 5

            # Bonus cho keywords chuyên môn cao
            tech_keywords = ['developer', 'engineer', 'programmer', 'software', 'fullstack',
                           'backend', 'frontend', 'devops', 'architect', 'lead', 'manager']
            if any(kw in desc for kw in tech_keywords):
                score += 4

            # Mô tả chi tiết
            if desc_len > 500:
                score += 6
            elif desc_len > 300:
                score += 4
            elif desc_len > 150:
                score += 2

        return min(score, 30)

    @staticmethod
    def score_projects(project_name, project_description, project_technologies):
        """
        Chấm điểm dự án: 0-35 điểm
        - Số lượng dự án: 0-10 điểm
        - Chất lượng mô tả: 0-10 điểm
        - Công nghệ sử dụng: 0-15 điểm
        """
        score = 0

        # 1. ĐẾM SỐ LƯỢNG DỰ ÁN THỰC TẾ (không chỉ xem length)
        project_count = 0

        # Detect từ project_name
        if not pd.isna(project_name) and len(str(project_name).strip()) > 0:
            project_text = str(project_name)

            # Count by separators
            if '\n' in project_text:
                project_count = len([p for p in project_text.split('\n') if p.strip()])
            elif ';' in project_text:
                project_count = len([p for p in project_text.split(';') if p.strip()])
            else:
                project_count = 1

        # Detect từ project_description (nếu có nhiều đoạn)
        if not pd.isna(project_description):
            desc_text = str(project_description)
            # Heuristic: mỗi 300-500 ký tự ~ 1 dự án có mô tả đầy đủ
            estimated_from_desc = max(1, len(desc_text) // 400)
            project_count = max(project_count, estimated_from_desc)

        # Điểm theo số lượng dự án
        if project_count >= 5:
            score += 10
        elif project_count >= 3:
            score += 8
        elif project_count >= 2:
            score += 6
        elif project_count >= 1:
            score += 4

        # 2. Chất lượng mô tả dự án
        if not pd.isna(project_description):
            desc_len = len(str(project_description))
            if desc_len > 800:  # Nhiều dự án mô tả chi tiết
                score += 10
            elif desc_len > 500:
                score += 8
            elif desc_len > 300:
                score += 6
            elif desc_len > 150:
                score += 4

        # 3. Công nghệ sử dụng (quan trọng nhất)
        if not pd.isna(project_technologies):
            tech_str = str(project_technologies).lower()

            # Công nghệ hiện đại cao cấp (DevOps, Cloud, CI/CD)
            modern_tech = ['docker', 'kubernetes', 'microservice', 'ci/cd', 'jenkins',
                          'github actions', 'gitlab ci', 'aws', 'azure', 'gcp', 'cloud',
                          'redis', 'kafka', 'websocket', 'graphql', 'oauth', 'jwt', 'firebase']
            modern_count = sum(1 for tech in modern_tech if tech in tech_str)
            score += min(modern_count * 2, 8)  # Tối đa +8

            # Fullstack bonus (frontend + backend + database)
            has_frontend = any(x in tech_str for x in ['react', 'vue', 'angular', 'frontend', 'tailwind'])
            has_backend = any(x in tech_str for x in ['node', 'express', 'spring', 'django', 'backend', '.net', 'flask'])
            has_database = any(x in tech_str for x in ['mongodb', 'mysql', 'postgresql', 'sql', 'database', 'firestore', 'sqlite'])

            if has_frontend and has_backend and has_database:
                score += 5  # Fullstack engineer

            # Số lượng công nghệ đa dạng
            tech_count = len(tech_str.split(';')) if ';' in tech_str else len(tech_str.split(','))
            if tech_count >= 6:
                score += 2
            elif tech_count >= 4:
                score += 1

        return min(score, 35)

    @staticmethod
    def score_skills(skills_list):
        """Chấm điểm kỹ năng: 0-20 điểm (tăng từ 15)"""
        if pd.isna(skills_list):
            return 5

        skills_str = str(skills_list).lower()
        
        # Điểm cơ bản theo số lượng
        skills_count = len(skills_str.split(';')) if ';' in skills_str else len(skills_str.split('\n'))
        base_score = min(skills_count * 1.5, 10)
        
        # Bonus cho kỹ năng hiện đại
        modern_skills = ['docker', 'kubernetes', 'microservices', 'cloud', 'aws', 'azure',
                        'react', 'vue', 'angular', 'node.js', 'python', 'java', 
                        'mongodb', 'redis', 'kafka', 'ci/cd', 'devops']
        bonus = sum(1 for skill in modern_skills if skill in skills_str)
        
        return min(base_score + bonus, 20)

    @staticmethod
    def score_certificates(certificates_text):
        """
        Chấm điểm chứng chỉ: 0-15 điểm
        - Phân biệt chứng chỉ quốc tế vs địa phương
        - Đếm số lượng chứng chỉ
        """
        if pd.isna(certificates_text) or len(str(certificates_text).strip()) == 0:
            return 0

        cert_str = str(certificates_text).lower()
        score = 0

        # Chứng chỉ quốc tế uy tín (mỗi cái +4 điểm)
        international_certs = [
            'coursera', 'edx', 'udacity', 'udemy', 'linkedin learning',
            'aws certified', 'google cloud', 'microsoft azure', 'cisco',
            'comptia', 'cfa', 'cpa', 'pmp', 'scrum master', 'agile',
            'ielts', 'toefl', 'toeic', 'british council', 'aptis',
            'cambridge', 'tesol', 'tefl', 'jlpt', 'topik'
        ]
        intl_count = sum(1 for cert in international_certs if cert in cert_str)
        score += min(intl_count * 4, 12)  # Tối đa 12 điểm

        # Đếm số lượng chứng chỉ (heuristic) - XỬ LÝ TEXT ĐÃ BỊ NORMALIZE (không khoảng trắng)
        cert_indicators = ['chứngchỉ', 'chứng chỉ', 'certificate', 'certification', 'certified', 'ứngchỉ']
        cert_count = sum(cert_str.count(indicator) for indicator in cert_indicators)

        if cert_count >= 3:
            score += 3
        elif cert_count >= 2:
            score += 2
        elif cert_count >= 1:
            score += 1

        return min(score, 15)

    @staticmethod
    def score_awards(awards_text):
        """
        Chấm điểm giải thưởng: 0-15 điểm
        - Giải thưởng kỹ thuật (ICPC, Hackathon) có giá trị cao hơn
        - Giải thưởng khác (sinh viên 5 tốt, etc.)
        """
        if pd.isna(awards_text) or len(str(awards_text).strip()) == 0:
            return 0

        award_str = str(awards_text).lower()
        score = 0

        # Giải thưởng kỹ thuật cao cấp (mỗi cái +6 điểm)
        tech_awards = [
            'icpc', 'hackathon', 'code challenge', 'programming contest',
            'olympiad', 'google code jam', 'facebook hacker cup',
            'topcoder', 'codeforces', 'kaggle', 'ai competition'
        ]
        tech_count = sum(1 for award in tech_awards if award in award_str)
        score += min(tech_count * 6, 12)  # Tối đa 12 điểm

        # Giải thưởng khác (học tập, đoàn thể) - XỬ LÝ TEXT ĐÃ BỊ NORMALIZE
        other_awards = [
            'giải', 'thưởng', 'award', 'prize', 'winner', 'champion',
            'sinhviên5tốt', 'sinh viên 5 tốt', 'sinhviêntiêntiến', 'sinh viên tiên tiến',
            'thànhtích', 'thành tích', 'thanhnhiêntiêntiến', 'thanh niên tiên tiến',
            'top 100', 'top 10', 'top 3', 'first prize', 'second prize',
            'excellent student', 'honor student', 'loạigiỏi', 'loại giỏi'
        ]
        other_count = sum(1 for award in other_awards if award in award_str)

        if other_count >= 3:
            score += 5
        elif other_count >= 2:
            score += 3
        elif other_count >= 1:
            score += 2

        return min(score, 15)

    @staticmethod
    def score_scholarships(education_text, awards_text):
        """
        Chấm điểm học bổng: 0-8 điểm
        """
        score = 0

        all_text = f"{str(education_text)} {str(awards_text)}".lower()

        scholarship_keywords = [
            'học bổng', 'scholarship', 'grant', 'fellowship',
            'sponsored', 'merit-based', 'need-based'
        ]

        scholarship_count = sum(all_text.count(kw) for kw in scholarship_keywords)

        if scholarship_count >= 3:
            score += 8
        elif scholarship_count >= 2:
            score += 6
        elif scholarship_count >= 1:
            score += 4

        return min(score, 8)

    @staticmethod
    def score_links(links_text):
        """
        Chấm điểm links (GitHub, Portfolio, LinkedIn): 0-10 điểm
        """
        if pd.isna(links_text) or len(str(links_text).strip()) == 0:
            return 0

        links_str = str(links_text).lower()
        score = 0

        # GitHub (rất quan trọng cho IT)
        if 'github' in links_str:
            score += 5

        # Portfolio/Personal website
        if any(x in links_str for x in ['portfolio', 'website', 'blog', 'behance', 'dribbble']):
            score += 3

        # LinkedIn
        if 'linkedin' in links_str:
            score += 2

        # Other professional links
        if any(x in links_str for x in ['stackoverflow', 'medium', 'dev.to', 'kaggle']):
            score += 2

        return min(score, 10)

    @staticmethod
    def score_activities(activity_text):
        """
        Chấm điểm hoạt động: 0-7 điểm
        (CHỈ cho hoạt động, không gộp certificates/awards)
        """
        if pd.isna(activity_text) or len(str(activity_text).strip()) == 0:
            return 0

        activity_str = str(activity_text).lower()
        score = 0

        # Hoạt động tình nguyện, CLB, đoàn thể - XỬ LÝ TEXT ĐÃ BỊ NORMALIZE
        activity_keywords = [
            'tìnhnguyện', 'tình nguyện', 'volunteer', 'clb', 'club', 'member',
            'thànhviên', 'thành viên', 'organizer', 'coordinator', 'leader',
            'hiếnmáu', 'hiến máu', 'trồngcây', 'trồng cây',
            'hoạtđộng', 'hoạt động', 'activity', 'nhặtrác', 'nhặt rác',
            'phongtrào', 'phong trào', 'thamgia', 'tham gia'
        ]

        activity_count = sum(1 for kw in activity_keywords if kw in activity_str)

        if activity_count >= 3:
            score += 7
        elif activity_count >= 2:
            score += 5
        elif activity_count >= 1:
            score += 3

        return min(score, 7)

    @staticmethod
    def score_contact_info(email, phone):
        """Chấm điểm thông tin liên hệ: 0-5 điểm"""
        score = 0
        if not pd.isna(email) and '@' in str(email):
            score += 2.5
        if not pd.isna(phone) and len(str(phone).replace(' ', '')) >= 9:
            score += 2.5
        return score

    @staticmethod
    def calculate_total_score(row):
        """
        Tính tổng điểm cho một CV (0-100) với industry-specific adjustments

        HỆ THỐNG CHẤM ĐIỂM MỚI (đọc đủ hết thông tin):
        - GPA: 0-10đ
        - Education: 0-10đ
        - Experience: 0-30đ (parse date chính xác)
        - Projects: 0-35đ (đếm số lượng)
        - Skills: 0-20đ
        - Certificates: 0-15đ (quốc tế vs địa phương)
        - Awards: 0-15đ (kỹ thuật vs khác)
        - Scholarships: 0-8đ
        - Links: 0-10đ (GitHub, Portfolio)
        - Activities: 0-7đ
        - Contact: 0-5đ
        ─────────────
        Tổng: ~165đ → scale về 0-100 + bonuses
        """

        # 1. Detect industry, seniority, và student status
        industry, confidence = CVScoringRules.detect_industry(row)
        seniority = CVScoringRules.detect_seniority(row)
        student_status = detect_student_status(row)  # 'Student', 'Graduated', 'Unknown'

        # 2. Base scores (đọc đủ hết thông tin)
        scores = {
            'gpa': CVScoringRules.score_gpa(row.get('gpa'), seniority),  # 0-10
            'education': CVScoringRules.score_education(row.get('education_level')),  # 0-10
            'experience': CVScoringRules.score_experience(  # 0-30 (parse date chính xác)
                row.get('job_description'),
                row.get('start_date'),
                row.get('end_date')
            ),
            'projects': CVScoringRules.score_projects(  # 0-35 (đếm số lượng)
                row.get('project_name'),
                row.get('project_description'),
                row.get('project_technologies')
            ),
            'skills': CVScoringRules.score_skills(row.get('skills_list')),  # 0-20
            'certificates': CVScoringRules.score_certificates(
                row.get('certificates') if row.get('certificates') else row.get('activity_certificate')
            ),  # 0-15
            'awards': CVScoringRules.score_awards(
                row.get('awards') if row.get('awards') else row.get('activity_certificate')
            ),  # 0-15
            'scholarships': CVScoringRules.score_scholarships(  # 0-8
                row.get('education_level'),
                row.get('awards') if row.get('awards') else row.get('activity_certificate')
            ),
            'links': CVScoringRules.score_links(row.get('links')),  # 0-10
            'activities': CVScoringRules.score_activities(
                row.get('activities') if row.get('activities') else row.get('activity_certificate')
            ),  # 0-7
            'contact': CVScoringRules.score_contact_info(row.get('email'), row.get('phone')),  # 0-5
        }

        # 3. Quantified achievements bonus
        achievement_score = CVScoringRules.detect_quantified_achievements(row)

        # 4. Student vs Graduated adjustments (THEO THỊ TRƯỜNG THỰC TẾ)
        student_adjustment = 0

        if student_status == 'Student':
            # Sinh viên: GPA, Projects, Awards, Certificates quan trọng hơn Experience
            if scores['gpa'] >= 8.5:
                student_adjustment += 5
            if scores['projects'] >= 20:
                student_adjustment += 8
            if scores['awards'] >= 10:
                student_adjustment += 5
            if scores['certificates'] >= 10:
                student_adjustment += 4
            # Giảm yêu cầu về experience
            if scores['experience'] < 10:
                student_adjustment += 3  # Bonus vì sinh viên không cần nhiều exp

        elif student_status == 'Graduated':
            # Đã tốt nghiệp: Experience, Skills thực tế quan trọng hơn
            if scores['experience'] >= 20:
                student_adjustment += 10
            if scores['skills'] >= 15:
                student_adjustment += 5
            # GPA ít quan trọng hơn
            if scores['gpa'] >= 9:
                student_adjustment += 2  # Vẫn có bonus nhưng ít hơn

        # 5. Industry-specific adjustments (NÂNG CẤP - theo thị trường thực tế)
        industry_bonus = 0
        red_flag_penalty = 0

        if industry in ['IT/Software', 'Data/AI', 'Security', 'QA/Testing']:
            # Tech industries: Projects + Skills + GitHub (ƯU TIÊN CAO)
            if scores['projects'] >= 25:
                industry_bonus += 15  # Tăng từ 8 → 15
            elif scores['projects'] >= 20:
                industry_bonus += 10
            elif scores['projects'] >= 15:
                industry_bonus += 6
            
            if scores['skills'] >= 15:
                industry_bonus += 8  # Tăng từ 5 → 8
            elif scores['skills'] >= 10:
                industry_bonus += 5
            
            if scores['links'] >= 5:  # GitHub
                industry_bonus += 6  # Tăng từ 4 → 6
            
            if scores['certificates'] >= 10:  # Tech certs
                industry_bonus += 3
            
            industry_bonus += achievement_score * 0.8  # Tăng từ 0.5 → 0.8
            
            # RED FLAG: Mid+ không có GitHub
            links_text = str(row.get('links', '')).lower()
            if seniority in ['Mid', 'Senior']:
                if 'github' not in links_text and 'gitlab' not in links_text:
                    red_flag_penalty += 10

        elif industry in ['Sales', 'Marketing']:
            # Sales/Marketing: Experience + Achievements (CRITICAL)
            if scores['experience'] >= 20:
                industry_bonus += 15  # Tăng từ 10 → 15
            elif scores['experience'] >= 15:
                industry_bonus += 10
            
            if scores['awards'] >= 8:
                industry_bonus += 6  # Tăng từ 5 → 6
            
            # Quantified achievements CRITICAL
            industry_bonus += achievement_score * 1.5  # Tăng từ 1.2 → 1.5
            
            # RED FLAG: Không có số liệu cụ thể
            job_desc = str(row.get('job_description', '')).lower()
            if not any(indicator in job_desc for indicator in ['%', '$', 'increased', 'improved', 'achieved', 'exceeded']):
                red_flag_penalty += 20

        elif industry == 'Design':
            # Design: Portfolio CRITICAL
            if scores['links'] >= 5:  # Behance, Dribbble
                industry_bonus += 15  # Tăng từ 5 → 15
            elif scores['links'] >= 3:
                industry_bonus += 8
            
            if scores['projects'] >= 20:
                industry_bonus += 12  # Tăng từ 10 → 12
            elif scores['projects'] >= 15:
                industry_bonus += 8
            
            # RED FLAG: Không có portfolio
            links_text = str(row.get('links', '')).lower()
            if not any(site in links_text for site in ['behance', 'dribbble', 'portfolio', 'figma']):
                red_flag_penalty += 40  # DEALBREAKER!

        elif industry in ['Finance', 'HR']:
            # Finance/HR: Certifications + Education (BẮT BUỘC)
            if scores['certificates'] >= 12:
                industry_bonus += 12  # Tăng từ 8 → 12
            elif scores['certificates'] >= 8:
                industry_bonus += 8
            
            if scores['gpa'] >= 8:
                industry_bonus += 6  # Tăng từ 5 → 6
            
            # RED FLAG: Finance không có cert
            if industry == 'Finance':
                certs = str(row.get('certificates', ''))
                if len(certs.strip()) < 20:
                    red_flag_penalty += 15

        elif industry == 'Product':
            # Product: Balance
            if scores['experience'] >= 20:
                industry_bonus += 12  # Tăng từ 8 → 12
            elif scores['experience'] >= 18:
                industry_bonus += 8
            if scores['projects'] >= 20:
                industry_bonus += 8
            industry_bonus += achievement_score * 0.9
            
            # SQL/Analytics tools CRITICAL for PM
            skills_text = str(row.get('skills_list', '')).lower()
            pm_skills = ['sql', 'mixpanel', 'amplitude', 'jira', 'confluence', 'analytics']
            if any(skill in skills_text for skill in pm_skills):
                industry_bonus += 5

        # 6. INDUSTRY-SPECIFIC ENHANCEMENTS (Tăng cường cho 5 ngành hiện có)
        
        # 6a. Data/AI - Tăng cường
        if industry == 'Data/AI':
            awards_text = str(row.get('awards', '') or row.get('activity_certificate', '')).lower()
            certs_text = str(row.get('certificates', '') or row.get('activity_certificate', '')).lower()
            
            # Kaggle/Competition bonus
            if 'kaggle' in awards_text or 'competition' in awards_text:
                industry_bonus += 8
            
            # Publications bonus
            if 'paper' in awards_text or 'publication' in awards_text or 'conference' in awards_text:
                industry_bonus += 6
            
            # ML Certificates (Coursera, TensorFlow, PyTorch)
            ml_certs = ['coursera', 'tensorflow', 'pytorch', 'fast.ai', 'deeplearning.ai', 
                       'machine learning', 'deep learning', 'andrew ng']
            ml_cert_count = sum(1 for cert in ml_certs if cert in certs_text)
            industry_bonus += ml_cert_count * 3  # +3đ mỗi ML cert
        
        # 6b. HR - Điều chỉnh
        if industry == 'HR':
            certs_text = str(row.get('certificates', '') or row.get('activity_certificate', '')).lower()
            
            # HR certifications CRITICAL
            hr_certs = ['shrm', 'hrci', 'cipd', 'phr', 'sphr', 'certified professional']
            if not any(cert in certs_text for cert in hr_certs) and seniority in ['Mid', 'Senior']:
                red_flag_penalty += 10  # Senior HR PHẢI có cert
            
            # Giảm GPA importance (đã tính ở trên, giờ bù trừ lại)
            if scores['gpa'] >= 8:
                industry_bonus -= 3  # Bù trừ bonus +6 ở trên → net +3
        
        # 6c. QA/Testing - Tăng cường
        if industry == 'QA/Testing':
            skills_text = str(row.get('skills_list', '')).lower()
            certs_text = str(row.get('certificates', '') or row.get('activity_certificate', '')).lower()
            
            # Automation tools CRITICAL
            qa_tools = ['selenium', 'cypress', 'appium', 'jmeter', 'postman', 'rest assured', 'k6']
            qa_count = sum(1 for tool in qa_tools if tool in skills_text)
            industry_bonus += qa_count * 3  # +3đ mỗi automation tool
            
            # ISTQB certification
            if 'istqb' in certs_text:
                industry_bonus += 8
        
        # 6d. Security - Tăng cường
        if industry == 'Security':
            certs_text = str(row.get('certificates', '') or row.get('activity_certificate', '')).lower()
            awards_text = str(row.get('awards', '') or row.get('activity_certificate', '')).lower()
            links_text = str(row.get('links', '')).lower()
            
            # Security certificates CRITICAL
            sec_certs = ['ceh', 'oscp', 'cissp', 'cism', 'comptia security', 'security+', 'cisa']
            sec_cert_count = sum(1 for cert in sec_certs if cert in certs_text)
            industry_bonus += sec_cert_count * 8  # +8đ mỗi security cert (cao!)
            
            # Bug bounty bonus
            if 'bug bounty' in awards_text or 'hackerone' in links_text or 'bugcrowd' in links_text:
                industry_bonus += 10
            
            # RED FLAG: Security Mid+ không có cert
            if sec_cert_count == 0 and seniority in ['Mid', 'Senior']:
                red_flag_penalty += 20
        
        # 6e. Finance - Tăng cường
        if industry == 'Finance':
            skills_text = str(row.get('skills_list', '')).lower()
            
            # Excel/SQL/Python CRITICAL for Finance
            finance_tech_skills = ['excel', 'sql', 'python', 'vba', 'power bi', 'tableau', 'financial modeling']
            tech_count = sum(1 for skill in finance_tech_skills if skill in skills_text)
            industry_bonus += tech_count * 2  # +2đ mỗi technical skill
        
        # 6f. Marketing - Tăng cường
        if industry == 'Marketing':
            certs_text = str(row.get('certificates', '') or row.get('activity_certificate', '')).lower()
            
            # Google Ads, Facebook Blueprint CRITICAL
            marketing_certs = ['google ads', 'facebook blueprint', 'hubspot', 'google analytics', 
                             'meta blueprint', 'google certified']
            if any(cert in certs_text for cert in marketing_certs):
                industry_bonus += 8  # Bonus lớn cho marketing certs
        
        # 7. NGÀNH MỚI - Content Writer/Creator
        if industry == 'Content':
            links_text = str(row.get('links', '')).lower()
            skills_text = str(row.get('skills_list', '')).lower()
            
            # Portfolio CRITICAL
            content_platforms = ['medium', 'substack', 'youtube', 'tiktok', 'blog', 'wordpress']
            has_portfolio = any(platform in links_text for platform in content_platforms)
            
            if has_portfolio:
                industry_bonus += 12
            else:
                red_flag_penalty += 15  # No portfolio = red flag
            
            # SEO skills
            if 'seo' in skills_text:
                industry_bonus += 8
            
            # Quantified reach (views, subscribers)
            industry_bonus += achievement_score * 1.3
        
        # 8. NGÀNH MỚI - Customer Service/Support
        elif industry == 'Customer Service':
            skills_text = str(row.get('skills_list', '')).lower()
            job_desc = str(row.get('job_description', '')).lower()
            
            # Experience CRITICAL
            if scores['experience'] >= 15:
                industry_bonus += 10
            
            # CS tools
            cs_tools = ['zendesk', 'intercom', 'freshdesk', 'helpscout', 'salesforce service']
            if any(tool in skills_text for tool in cs_tools):
                industry_bonus += 6
            
            # Quantified metrics (CSAT, NPS)
            if any(metric in job_desc for metric in ['csat', 'nps', 'satisfaction', 'customer rating']):
                industry_bonus += 8
        
        # 9. NGÀNH MỚI - Operations/Logistics
        elif industry == 'Operations':
            certs_text = str(row.get('certificates', '') or row.get('activity_certificate', '')).lower()
            job_desc = str(row.get('job_description', '')).lower()
            
            # Certificates (Six Sigma, APICS, Lean)
            ops_certs = ['six sigma', 'lean', 'apics', 'cpim', 'cscp', 'green belt', 'black belt']
            ops_cert_count = sum(1 for cert in ops_certs if cert in certs_text)
            industry_bonus += ops_cert_count * 5  # +5đ mỗi ops cert
            
            # Process improvement keywords
            process_keywords = ['optimize', 'improve', 'reduce cost', 'efficiency', 'productivity']
            if any(kw in job_desc for kw in process_keywords):
                industry_bonus += 8
        
        # 10. NGÀNH MỚI - Legal/Compliance
        elif industry == 'Legal':
            education_text = str(row.get('education_level', '')).lower()
            certs_text = str(row.get('certificates', '') or row.get('activity_certificate', '')).lower()
            job_title = str(row.get('job_title', '')).lower()
            
            # Law degree REQUIRED
            if 'law' not in education_text and 'legal' not in education_text and 'juris' not in education_text:
                red_flag_penalty += 50  # DEALBREAKER
            
            # Bar exam / Attorney
            if 'bar exam' in certs_text or 'attorney' in job_title or 'lawyer' in job_title:
                industry_bonus += 15
            
            # Experience CRITICAL
            if scores['experience'] >= 20:
                industry_bonus += 12
        
        # 11. NGÀNH MỚI - Healthcare
        elif industry == 'Healthcare':
            education_text = str(row.get('education_level', '')).lower()
            certs_text = str(row.get('certificates', '') or row.get('activity_certificate', '')).lower()
            
            # Medical license REQUIRED
            healthcare_keywords = ['license', 'licensed', 'md', 'rn', 'nurse', 'doctor', 'physician', 
                                  'registered nurse', 'medical degree', 'nursing degree']
            has_license = any(kw in certs_text or kw in education_text for kw in healthcare_keywords)
            
            if not has_license:
                red_flag_penalty += 60  # ABSOLUTE DEALBREAKER
            
            # Education CRITICAL (Master/PhD for doctors)
            if scores['education'] >= 9:  # Master/PhD
                industry_bonus += 15

        # 12. Seniority adjustments (TĂNG CƯỜNG + BỔ SUNG LEAD)
        if seniority == 'Lead':
            # Lead level: Leadership, Strategy, Mentoring CRITICAL
            exp_text = str(row.get('job_description', '')).lower()
            
            # Leadership keywords
            leadership_keywords = ['lead', 'principal', 'staff', 'architect', 'mentor', 'train',
                                 'team lead', 'tech lead', 'cross-team', 'strategy', 'roadmap',
                                 'mentoring', 'coaching', 'hiring', 'leading', 'managed team']
            leadership_count = sum(1 for kw in leadership_keywords if kw in exp_text)
            
            if leadership_count >= 5:
                industry_bonus += 15  # BONUS LỚN cho leadership
            elif leadership_count >= 3:
                industry_bonus += 10
            
            # Business impact CRITICAL for Lead
            if achievement_score >= 8:
                industry_bonus += 10  # DOUBLE impact cho Lead
            
            # Experience MUST be strong
            if scores['experience'] >= 28:
                industry_bonus += 8
        
        elif seniority == 'Senior':
            if scores['experience'] >= 25:
                industry_bonus += 6  # Tăng từ 4 → 6
            if scores['awards'] >= 10:
                industry_bonus += 4
        
        elif seniority == 'Entry':
            # Entry level adjustments
            if scores['projects'] >= 20:
                industry_bonus += 5  # Tăng từ 3 → 5
            if scores['gpa'] >= 8:
                industry_bonus += 3
            
            # Entry GitHub red flag (nhẹ hơn Mid/Senior)
            if industry in ['IT/Software', 'Data/AI']:
                links_text = str(row.get('links', '')).lower()
                if 'github' not in links_text and 'gitlab' not in links_text:
                    red_flag_penalty += 5  # Nhẹ hơn Mid/Senior (-10đ)

        # 13. Confidence bonus
        if confidence >= 10:
            industry_bonus += 4  # Tăng từ 3 → 4
        elif confidence >= 5:
            industry_bonus += 2  # Tăng từ 1 → 2

        # 8. Tính tổng điểm (scale về 0-100)
        base_total = sum(scores.values())

        # Scale: ~165 điểm tối đa → scale về ~75, sau đó + bonuses - red_flags
        scaled_score = (base_total / 165) * 75

        total = scaled_score + student_adjustment + industry_bonus + achievement_score - red_flag_penalty

        # Metadata (thêm red_flag_penalty)
        scores['achievement_bonus'] = achievement_score
        scores['student_adjustment'] = student_adjustment
        scores['industry_bonus'] = industry_bonus
        scores['red_flag_penalty'] = red_flag_penalty  # THÊM MỚI
        scores['detected_industry'] = industry
        scores['seniority'] = seniority
        scores['student_status'] = student_status

        return min(max(total, 0), 100), scores  # Clamp 0-100


class CVFeatureExtractor:
    """Trích xuất features từ CV để train model"""

    def __init__(self):
        self.tfidf_objective = TfidfVectorizer(max_features=50, ngram_range=(1, 2))
        self.tfidf_skills = TfidfVectorizer(max_features=30, ngram_range=(1, 1))
        self.tfidf_job_desc = TfidfVectorizer(max_features=40, ngram_range=(1, 2))

        self.education_encoder = LabelEncoder()
        self.major_encoder = LabelEncoder()

        self.fitted = False

    def extract_numerical_features(self, df):
        """Trích xuất features số"""
        features = pd.DataFrame()

        # GPA - Convert to numeric first, then fill missing values
        gpa_numeric = pd.to_numeric(df['gpa'], errors='coerce')
        gpa_median = gpa_numeric.median() if not gpa_numeric.isna().all() else 7.5
        features['gpa'] = gpa_numeric.fillna(gpa_median)

        # Graduation year (chuyển thành "years since graduation")
        current_year = datetime.now().year
        features['years_since_grad'] = current_year - pd.to_numeric(df['graduation_year'], errors='coerce').fillna(current_year)

        # Text length features
        features['objective_length'] = df['objective'].fillna('').astype(str).str.len()
        features['job_desc_length'] = df['job_description'].fillna('').astype(str).str.len()
        features['project_desc_length'] = df['project_description'].fillna('').astype(str).str.len()
        features['skills_count'] = df['skills_list'].fillna('').astype(str).str.count(';') + 1

        # Has features (binary)
        features['has_experience'] = (~df['company_name'].isna()).astype(int)
        features['has_project'] = (~df['project_name'].isna()).astype(int)
        features['has_activity'] = (~df['activity_certificate'].isna()).astype(int)
        features['has_email'] = df['email'].fillna('').astype(str).str.contains('@').astype(int)
        features['has_phone'] = (df['phone'].fillna('').astype(str).str.len() > 8).astype(int)

        return features

    def extract_categorical_features(self, df, fit=False):
        """Trích xuất features phân loại"""
        features = pd.DataFrame()

        # Education level
        edu_levels = df['education_level'].fillna('Unknown').astype(str)
        if fit:
            features['education_encoded'] = self.education_encoder.fit_transform(edu_levels)
        else:
            # Handle unknown categories
            features['education_encoded'] = edu_levels.map(
                lambda x: self.education_encoder.transform([x])[0]
                if x in self.education_encoder.classes_
                else -1
            )

        # Major (simplified - just check if CS/IT related)
        major_keywords = ['phần mềm', 'máy tính', 'công nghệ', 'khoa học', 'dữ liệu',
                         'software', 'computer', 'technology', 'data', 'it']
        features['is_tech_major'] = df['major'].fillna('').astype(str).str.lower().apply(
            lambda x: int(any(kw in x for kw in major_keywords))
        )

        return features

    def extract_text_features(self, df, fit=False):
        """Trích xuất features từ text (TF-IDF)"""
        # Objective
        objective_text = df['objective'].fillna('').astype(str)
        if fit:
            objective_tfidf = self.tfidf_objective.fit_transform(objective_text).toarray()
        else:
            objective_tfidf = self.tfidf_objective.transform(objective_text).toarray()

        # Skills
        skills_text = df['skills_list'].fillna('').astype(str)
        if fit:
            skills_tfidf = self.tfidf_skills.fit_transform(skills_text).toarray()
        else:
            skills_tfidf = self.tfidf_skills.transform(skills_text).toarray()

        # Job description
        job_desc_text = df['job_description'].fillna('').astype(str)
        if fit:
            job_tfidf = self.tfidf_job_desc.fit_transform(job_desc_text).toarray()
        else:
            job_tfidf = self.tfidf_job_desc.transform(job_desc_text).toarray()

        # Combine
        text_features = np.hstack([objective_tfidf, skills_tfidf, job_tfidf])

        return pd.DataFrame(
            text_features,
            columns=[f'text_feat_{i}' for i in range(text_features.shape[1])]
        )

    def extract_features(self, df, fit=False):
        """Trích xuất tất cả features"""
        numerical = self.extract_numerical_features(df)
        categorical = self.extract_categorical_features(df, fit=fit)
        text = self.extract_text_features(df, fit=fit)

        # Combine all features
        all_features = pd.concat([numerical, categorical, text], axis=1)

        if fit:
            self.fitted = True

        return all_features


class CVScoringModel:
    """Model AI để chấm điểm CV"""

    def __init__(self):
        self.feature_extractor = CVFeatureExtractor()
        self.scaler = StandardScaler()

        if USE_XGBOOST:
            self.model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42
            )
        else:
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )

        self.trained = False

    def train(self, training_csv_paths):
        """Train model từ CSV files"""
        print("\n" + "="*80)
        print("🧠 TRAINING THE BRAIN - Huấn luyện mô hình AI")
        print("="*80)

        # Load training data
        print("\n📂 Đang load dữ liệu training...")
        dfs = []
        for path in training_csv_paths:
            df = pd.read_csv(path, encoding='utf-8-sig')
            dfs.append(df)
            print(f"   ✓ {os.path.basename(path)}: {len(df)} CVs")

        training_df = pd.concat(dfs, ignore_index=True)
        print(f"\n📊 Tổng số CV training: {len(training_df)}")

        # Generate scores using rules
        print("\n🎯 Đang tạo điểm tự động bằng scoring rules...")
        scores = []
        score_details = []

        for idx, row in training_df.iterrows():
            total_score, breakdown = CVScoringRules.calculate_total_score(row)
            scores.append(total_score)
            score_details.append(breakdown)

        training_df['target_score'] = scores

        print(f"   ✓ Điểm trung bình: {np.mean(scores):.2f}/100")
        print(f"   ✓ Điểm thấp nhất: {np.min(scores):.2f}")
        print(f"   ✓ Điểm cao nhất: {np.max(scores):.2f}")

        # Extract features
        print("\n🔧 Đang trích xuất features...")
        X = self.feature_extractor.extract_features(training_df, fit=True)
        y = training_df['target_score'].values

        print(f"   ✓ Số lượng features: {X.shape[1]}")

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42
        )

        print(f"   ✓ Training set: {len(X_train)} samples")
        print(f"   ✓ Test set: {len(X_test)} samples")

        # Train model
        model_name = "XGBoost" if USE_XGBOOST else "Random Forest"
        print(f"\n🚀 Đang train {model_name} model...")

        self.model.fit(X_train, y_train)

        # Evaluate
        train_score = self.model.score(X_train, y_train)
        test_score = self.model.score(X_test, y_test)

        y_pred = self.model.predict(X_test)
        mae = np.mean(np.abs(y_test - y_pred))

        print(f"\n📈 Kết quả đánh giá:")
        print(f"   ✓ R² score (train): {train_score:.4f}")
        print(f"   ✓ R² score (test):  {test_score:.4f}")
        print(f"   ✓ MAE (test):       {mae:.2f} điểm")

        self.trained = True

        print("\n✅ Training hoàn tất!")

        return {
            'train_r2': train_score,
            'test_r2': test_score,
            'mae': mae,
            'n_samples': len(training_df),
            'n_features': X.shape[1]
        }

    def predict(self, cv_data):
        """Predict score cho CV mới"""
        if not self.trained:
            raise Exception("Model chưa được train!")

        # Convert dict to DataFrame
        if isinstance(cv_data, dict):
            df = pd.DataFrame([cv_data])
        else:
            df = cv_data

        # Extract features
        X = self.feature_extractor.extract_features(df, fit=False)
        X_scaled = self.scaler.transform(X)

        # Predict
        score = self.model.predict(X_scaled)[0]

        return max(0, min(100, score))  # Clamp to 0-100

    def save_model(self, filepath='thebrain_model.pkl'):
        """Lưu model"""
        model_data = {
            'model': self.model,
            'feature_extractor': self.feature_extractor,
            'scaler': self.scaler,
            'trained': self.trained
        }
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
        print(f"✅ Đã lưu model vào: {filepath}")

    @staticmethod
    def load_model(filepath='thebrain_model.pkl'):
        """Load model đã train"""
        if not os.path.exists(filepath):
            return None

        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)

        scoring_model = CVScoringModel()
        scoring_model.model = model_data['model']
        scoring_model.feature_extractor = model_data['feature_extractor']
        scoring_model.scaler = model_data['scaler']
        scoring_model.trained = model_data['trained']

        print(f"✅ Đã load model từ: {filepath}")
        return scoring_model


def convert_read_cv4_to_dataframe(cv_info):
    """
    Chuyển đổi output của read_cv4 sang format DataFrame
    QUAN TRỌNG: Giữ các field riêng biệt để scoring functions đọc đúng
    """
    # Ghép projects và technologies để scoring nhận diện được
    projects_text = str(cv_info.get('projects', ''))

    # GỘP cho activity_certificate (cho backward compatibility với training data)
    combined_activities = ' '.join(filter(None, [
        str(cv_info.get('certificates', '')),
        str(cv_info.get('activities', '')),
        str(cv_info.get('awards', ''))
    ]))

    return {
        'cv_id': 'NEW_CV',
        'full_name': cv_info.get('info', ''),
        'email': cv_info.get('email'),
        'phone': cv_info.get('phone'),
        'links': ';'.join(cv_info.get('links', [])) if cv_info.get('links') else None,
        'objective': cv_info.get('objective'),
        'education_level': cv_info.get('education'),
        'school_name': cv_info.get('education'),
        'major': cv_info.get('education'),
        'graduation_year': None,  # read_cv4 không trích xuất riêng
        'gpa': cv_info.get('gpa'),
        'company_name': cv_info.get('experience'),
        'job_title': cv_info.get('experience'),
        'start_date': None,
        'end_date': None,
        'job_description': cv_info.get('experience'),
        'project_name': projects_text,  # Dùng toàn bộ text
        'project_role': projects_text,
        'project_technologies': projects_text,  # Chứa tất cả công nghệ
        'project_description': projects_text,
        'skills_list': cv_info.get('skills'),
        'activity_certificate': combined_activities,  # GỘP cho training data compatibility
        # THÊM CÁC FIELD RIÊNG BIỆT cho scoring functions
        'certificates': cv_info.get('certificates', ''),
        'awards': cv_info.get('awards', ''),
        'activities': cv_info.get('activities', ''),
    }


def score_new_cv_from_pdf(pdf_path, model, target_job_level='Mid'):
    """
    Chấm điểm CV mới từ file PDF
    
    Args:
        pdf_path: Đường dẫn file PDF
        model: Model đã train
        target_job_level: Vị trí ứng tuyển ('Intern', 'Entry', 'Mid', 'Senior', 'Lead')
    """
    print(f"\n{'='*60}")
    print(f"📄 Đang phân tích: {os.path.basename(pdf_path)}")
    print(f"{'='*60}")

    # Bước 1: Đọc CV bằng read_cv4
    print("\n🔍 Bước 1: Đọc và trích xuất thông tin CV...")
    cv_text = extract_text_from_pdf(pdf_path)

    if not cv_text:
        print(f"❌ Không thể đọc file PDF")
        return None

    cv_info = extract_key_info(cv_text)
    print("   ✓ Trích xuất thành công")

    # Bước 2: Chuyển đổi sang format DataFrame
    cv_data = convert_read_cv4_to_dataframe(cv_info)
    
    # Detect industry và seniority
    industry, confidence = CVScoringRules.detect_industry(cv_data)
    candidate_seniority = CVScoringRules.detect_seniority(cv_data)

    # Bước 3: Predict base score và lấy breakdown
    print("\n🤖 Bước 2: AI đang phân tích và chấm điểm...")

    # Get detailed scoring breakdown
    total_score, score_breakdown = CVScoringRules.calculate_total_score(cv_data)
    base_score = model.predict(cv_data)

    # Bước 4: Adjust score based on job-CV match
    match_adjustment = calculate_job_match_adjustment(candidate_seniority, target_job_level, base_score)
    final_score = base_score + match_adjustment

    # Bước 5: Hiển thị kết quả CHI TIẾT
    print("\n" + "="*70)
    print("📊 KẾT QUẢ PHÂN TÍCH CHI TIẾT")
    print("="*70)

    print(f"\n🏢 NGÀNH NGHỀ: {industry}")
    print(f"👤 CẤP BẬC ỨNG VIÊN: {candidate_seniority}")
    print(f"📚 TÌNH TRẠNG: {score_breakdown.get('student_status', 'Unknown')}")
    print(f"🎯 VỊ TRÍ ỨNG TUYỂN: {target_job_level}")

    # Match assessment
    if match_adjustment > 0:
        print(f"✅ MATCH: Phù hợp (+{match_adjustment:.1f} điểm)")
    elif match_adjustment < 0:
        print(f"⚠️  MISMATCH: Không phù hợp ({match_adjustment:.1f} điểm)")
    else:
        print(f"➖ MATCH: Trung bình (0 điểm)")

    if confidence > 0:
        print(f"   Industry confidence: {confidence} keyword(s)")

    # HIỂN THỊ RED FLAGS (THÊM MỚI)
    red_flag_penalty = score_breakdown.get('red_flag_penalty', 0)
    if red_flag_penalty > 0:
        print(f"\n🚩 RED FLAGS DETECTED:")
        print(f"   ❌ Phát hiện vấn đề nghiêm trọng")
        print(f"   Penalty: -{red_flag_penalty} điểm")
        
        # Giải thích red flag
        if industry == 'Design' and red_flag_penalty >= 40:
            print(f"   • KHÔNG CÓ PORTFOLIO (Behance/Dribbble) - DEALBREAKER!")
        elif industry in ['IT/Software', 'Data/AI'] and red_flag_penalty >= 10:
            print(f"   • Mid/Senior KHÔNG CÓ GITHUB - Red flag cho vị trí kỹ thuật")
        elif industry in ['Sales', 'Marketing'] and red_flag_penalty >= 20:
            print(f"   • KHÔNG CÓ SỐ LIỆU CỤ THỂ (%, $, metrics) - Thiếu quantified achievements")
        elif industry == 'Finance' and red_flag_penalty >= 15:
            print(f"   • KHÔNG CÓ CHỨNG CHỈ CHUYÊN NGHIỆP (CFA/CPA/ACCA)")

    print("\n🔍 THÔNG TIN ĐÃ TRÍCH XUẤT:")
    print(f"   📧 Email: {cv_info.get('email', 'N/A')}")
    print(f"   📱 Phone: {cv_info.get('phone', 'N/A')}")
    print(f"   🎓 GPA: {cv_info.get('gpa', 'N/A')}")

    if cv_info.get('links'):
        print(f"   🔗 Links: {len(cv_info['links'])} link(s)")

    sections = ['education', 'experience', 'projects', 'skills', 'activities', 'certificates']
    print("\n📝 CÁC PHẦN ĐÃ PHÁT HIỆN:")
    for section in sections:
        content = cv_info.get(section, '')
        if content and len(str(content).strip()) > 0:
            print(f"   ✓ {section.title()}: {len(content)} ký tự")

    # CHI TIẾT ĐIỂM SỐ TỪNG PHẦN (ĐỌC ĐỦ HẾT THÔNG TIN)
    print("\n" + "─"*70)
    print("📈 CHI TIẾT ĐIỂM SỐ (HỆ THỐNG MỚI - ĐỌC ĐỦ HẾT THÔNG TIN)")
    print("─"*70)

    score_items = [
        ('GPA', score_breakdown.get('gpa', 0), 10),
        ('Education', score_breakdown.get('education', 0), 10),
        ('Experience', score_breakdown.get('experience', 0), 30),
        ('Projects', score_breakdown.get('projects', 0), 35),
        ('Skills', score_breakdown.get('skills', 0), 20),
        ('Certificates', score_breakdown.get('certificates', 0), 15),
        ('Awards', score_breakdown.get('awards', 0), 15),
        ('Scholarships', score_breakdown.get('scholarships', 0), 8),
        ('Links (GitHub/Portfolio)', score_breakdown.get('links', 0), 10),
        ('Activities', score_breakdown.get('activities', 0), 7),
        ('Contact', score_breakdown.get('contact', 0), 5),
    ]

    for label, score, max_score in score_items:
        bar_length = int((score / max_score) * 30) if max_score > 0 else 0
        bar = '█' * bar_length + '░' * (30 - bar_length)
        print(f"   {label:.<28} {bar} {score:>5.1f}/{max_score}")

    print("\n   " + "─"*66)

    # Bonuses
    achievement = score_breakdown.get('achievement_bonus', 0)
    student_adj = score_breakdown.get('student_adjustment', 0)
    industry_bonus = score_breakdown.get('industry_bonus', 0)

    if achievement > 0:
        print(f"   Achievement Bonus (quantified results)  +{achievement:.1f}")
    if student_adj > 0:
        status = score_breakdown.get('student_status', 'Unknown')
        print(f"   {status} Adjustment                      +{student_adj:.1f}")
    if industry_bonus > 0:
        print(f"   Industry Bonus                           +{industry_bonus:.1f}")

    # Score và xếp loại
    print("\n" + "="*70)
    print(f"   📊 ĐIỂM CƠ BẢN (ML Model): {base_score:.2f}/100")
    if match_adjustment != 0:
        print(f"   🎯 ĐIỂM MATCH (Job Level): {match_adjustment:+.2f}")
    print(f"   🎯 ĐIỂM CUỐI CÙNG: {final_score:.2f}/100")

    percentage = final_score
    if percentage >= 85:
        grade = "XUẤT SẮC 🌟"
    elif percentage >= 70:
        grade = "TỐT ✅"
    elif percentage >= 55:
        grade = "KHÁ 👍"
    elif percentage >= 40:
        grade = "TRUNG BÌNH ⚠️"
    else:
        grade = "YẾU ❌"

    print(f"   🏅 XẾP LOẠI: {grade}")
    print("="*70 + "\n")

    return {
        'file_name': os.path.basename(pdf_path),
        'base_score': base_score,
        'match_adjustment': match_adjustment,
        'final_score': final_score,
        'grade': grade,
        'industry': industry,
        'candidate_seniority': candidate_seniority,
        'target_job_level': target_job_level,
        'cv_info': cv_info
    }


def calculate_job_match_adjustment(candidate_level, target_level, base_score):
    """
    Tính điểm điều chỉnh dựa trên sự phù hợp giữa level ứng viên và vị trí
    
    Logic (theo thị trường thực tế):
    - Overqualified: Có thể bị từ chối (boring job, flight risk)
    - Perfect match: Bonus
    - Underqualified: Penalty lớn
    """
    
    # Map levels to numeric values
    level_map = {
        'Intern': 0,
        'Entry': 1,
        'Mid': 2,
        'Senior': 3,
        'Lead': 4
    }
    
    candidate_num = level_map.get(candidate_level, 2)
    target_num = level_map.get(target_level, 2)
    
    gap = candidate_num - target_num
    
    # Perfect match
    if gap == 0:
        return 5  # Bonus cho perfect match
    
    # Underqualified (candidate < target)
    elif gap == -1:
        # 1 level below - có thể accept nếu base score cao
        if base_score >= 75:
            return -3  # Penalty nhẹ
        else:
            return -8  # Penalty nặng
    elif gap == -2:
        # 2 levels below - rất khó
        return -15
    elif gap <= -3:
        # 3+ levels below - hầu như không thể
        return -25
    
    # Overqualified (candidate > target)
    elif gap == 1:
        # 1 level above - OK, có thể accept
        if target_level in ['Intern', 'Entry']:
            # Entry người apply có experience - good!
            return 3
        else:
            # Mid apply Senior position - slight concern about fit
            return 0
    elif gap == 2:
        # 2 levels above - overqualified
        if target_level == 'Intern':
            # Senior apply Intern - red flag
            return -10
        else:
            # Overqualified but maybe OK
            return -5
    elif gap >= 3:
        # 3+ levels above - major concern
        return -15
    
    return 0



def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='THE BRAIN - AI Chấm Điểm CV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python thebrain.py cv.pdf                        # Chấm CV cho vị trí Mid-level (default)
  python thebrain.py cv.pdf --job-level Senior     # Chấm CV cho vị trí Senior
  python thebrain.py cv.pdf --job-level Intern     # Chấm CV cho vị trí Intern
  python thebrain.py --retrain                     # Train lại model
        """
    )
    parser.add_argument('files', nargs='*', help='File PDF CV cần chấm điểm')
    parser.add_argument('--retrain', action='store_true', help='Train lại model')
    parser.add_argument('--job-level', '--level', '-l', 
                       choices=['Intern', 'Entry', 'Mid', 'Senior', 'Lead'],
                       default='Mid',
                       help='Vị trí ứng tuyển (default: Mid)')
    
    args = parser.parse_args()

    model_path = 'thebrain_model.pkl'

    print("\n" + "="*80)
    print("🧠 THE BRAIN - AI Chấm Điểm CV (Phiên bản Machine Learning)")
    print("="*80)

    # Load hoặc train model
    if os.path.exists(model_path) and not args.retrain:
        model = CVScoringModel.load_model(model_path)
        if not model:
            print("❌ Không thể load model. Cần train lại.")
            return
    else:
        if args.retrain:
            print("\n🔄 Đang train lại model...")
        else:
            print("\n⚠️  Model chưa tồn tại. Đang train...")
        
        training_files = ['Sheet 1.csv', 'Sheet2.csv']
        model = CVScoringModel()
        model.train(training_files)
        model.save_model(model_path)
        print("\n✅ Hoàn tất!")
        
        if args.retrain:
            return

    # Nếu không có file input
    if not args.files:
        print("\n⚠️  Vui lòng chỉ định file CV để chấm điểm.")
        print("   Ví dụ: python thebrain.py cv.pdf --job-level Senior")
        return

    # Get list of PDF files
    pdf_files = []
    for pattern in args.files:
        if '*' in pattern or '?' in pattern:
            import glob
            pdf_files.extend(glob.glob(pattern))
        else:
            pdf_files.append(pattern)

    pdf_files = [f for f in pdf_files if f.lower().endswith('.pdf')]

    if not pdf_files:
        print("❌ Không tìm thấy file PDF nào!")
        return

    print(f"\n📂 Tìm thấy {len(pdf_files)} file PDF")
    print(f"🎯 Vị trí ứng tuyển: {args.job_level}")

    # Score từng CV
    results = []
    for pdf_file in pdf_files:
        if not os.path.exists(pdf_file):
            print(f"❌ File không tồn tại: {pdf_file}")
            continue

        result = score_new_cv_from_pdf(pdf_file, model, args.job_level)
        if result:
            results.append(result)

    # Summary table
    if len(results) > 1:
        print("\n" + "="*100)
        print("📊 BẢNG TỔNG HỢP")
        print("="*100 + "\n")

        results.sort(key=lambda x: x['final_score'], reverse=True)

        print(f"{'STT':<5} {'TÊN FILE':<30} {'NGÀNH':<13} {'LEVEL':<8} {'MATCH':<8} {'ĐIỂM':<10} {'LOẠI':<15}")
        print("-"*100)

        for idx, result in enumerate(results, 1):
            fname = result['file_name']
            if len(fname) > 28:
                fname = fname[:25] + "..."

            # Safe string conversion
            industry = str(result.get('industry', 'N/A'))[:11]
            candidate = str(result.get('candidate_seniority', 'N/A'))[:6]
            match_adj = result.get('match_adjustment', 0)
            match_str = f"{match_adj:+.1f}" if match_adj != 0 else "0"

            print(f"{idx:<5} {fname:<30} {industry:<13} {candidate:<8} {match_str:<8} "
                  f"{result['final_score']:>6.2f}/100  {result['grade']:<15}")

        print("="*100 + "\n")


if __name__ == "__main__":
    main()
