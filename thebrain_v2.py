"""
THE BRAIN V2 - Hệ thống AI phân tích và chấm điểm CV
PHIÊN BẢN MỚI: Dynamic weights theo ngành nghề và level

Key improvements:
- Industry-specific weights (IT trọng projects, Sales trọng achievements)
- Level-specific adjustments (Fresher vs Senior khác nhau)
- Quality-based experience scoring (không chỉ đếm năm)
- Enhanced portfolio detection
- Red flags detection
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

# Import từ thebrain.py cũ
try:
    from thebrain import (
        parse_date_flexible, calculate_months_between,
        detect_student_status, CVFeatureExtractor, CVScoringModel,
        convert_read_cv4_to_dataframe, calculate_job_match_adjustment
    )
    from read_cv4 import extract_text_from_pdf, extract_key_info
    import config
except ImportError as e:
    print(f"❌ Lỗi: Không thể import: {e}")
    sys.exit(1)


# ============================================================================
# V2: INDUSTRY-SPECIFIC WEIGHTS SYSTEM
# ============================================================================

INDUSTRY_WEIGHTS = {
    'IT/Software': {
        'projects': 0.40,
        'skills': 0.25,
        'experience': 0.20,
        'links': 0.10,      # GitHub
        'certificates': 0.03,
        'gpa': 0.02,
        'awards': 0.00,     # Không quan trọng
    },
    'Data/AI': {
        'projects': 0.35,    # Kaggle, research
        'skills': 0.30,
        'experience': 0.20,
        'education': 0.10,   # Degree matters
        'links': 0.03,
        'gpa': 0.02,
    },
    'Design': {
        'links': 0.45,       # Portfolio CRITICAL
        'projects': 0.30,
        'experience': 0.20,
        'skills': 0.05,
    },
    'Sales': {
        'experience': 0.35,
        'achievements': 0.30,  # Quantified results
        'activities': 0.15,    # Communication skills
        'skills': 0.10,
        'projects': 0.05,
        'gpa': 0.05,
    },
    'Marketing': {
        'experience': 0.30,
        'achievements': 0.25,
        'skills': 0.20,
        'projects': 0.15,
        'activities': 0.05,
        'gpa': 0.05,
    },
    'Finance': {
        'certificates': 0.35,  # CFA/CPA critical
        'experience': 0.30,
        'gpa': 0.20,
        'education': 0.10,
        'skills': 0.05,
    },
    'HR': {
        'experience': 0.40,
        'activities': 0.25,    # People skills
        'certificates': 0.15,
        'skills': 0.10,
        'gpa': 0.10,
    },
    'Product': {
        'experience': 0.35,
        'projects': 0.25,
        'skills': 0.20,
        'activities': 0.10,
        'gpa': 0.10,
    },
    'QA/Testing': {
        'skills': 0.35,
        'experience': 0.30,
        'certificates': 0.20,
        'projects': 0.15,
    },
    'Security': {
        'certificates': 0.35,
        'skills': 0.30,
        'experience': 0.25,
        'projects': 0.10,
    },
    'General': {  # Default fallback
        'experience': 0.30,
        'skills': 0.25,
        'projects': 0.20,
        'education': 0.15,
        'gpa': 0.10,
    }
}


# ============================================================================
# V2: ENHANCED SCORING FUNCTIONS
# ============================================================================

class CVScoringRulesV2:
    """V2: Industry-aware scoring với dynamic weights"""
    
    # Reuse từ V1
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
    }

    @staticmethod
    def detect_industry(cv_data):
        """Phát hiện ngành nghề từ CV"""
        text_fields = [
            str(cv_data.get('objective', '')),
            str(cv_data.get('job_description', '')),
            str(cv_data.get('job_title', '')),
            str(cv_data.get('project_description', '')),
            str(cv_data.get('skills_list', '')),
            str(cv_data.get('major', '')),
        ]
        full_text = ' '.join(text_fields).lower()
        
        industry_scores = {}
        for industry, keywords in CVScoringRulesV2.INDUSTRY_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in full_text)
            industry_scores[industry] = score
        
        if max(industry_scores.values()) > 0:
            detected_industry = max(industry_scores, key=industry_scores.get)
            return detected_industry, industry_scores[detected_industry]
        
        return 'General', 0

    @staticmethod
    def detect_seniority(cv_data):
        """Phát hiện seniority level từ CV"""
        exp_text = str(cv_data.get('job_description', ''))
        
        senior_keywords = ['senior', 'lead', 'principal', 'architect', 'head of', 'director', 'manager', 'chief']
        entry_keywords = ['intern', 'junior', 'trainee', 'fresher', 'graduate', 'entry']
        
        exp_lower = exp_text.lower()
        title_lower = str(cv_data.get('job_title', '')).lower()
        
        if any(keyword in title_lower for keyword in senior_keywords):
            return 'Senior'
        if any(keyword in title_lower for keyword in entry_keywords):
            return 'Entry'
            
        senior_count = sum(1 for k in senior_keywords if k in exp_lower)
        entry_count = sum(1 for k in entry_keywords if k in exp_lower)
        
        if senior_count >= 2:
            return 'Senior'
        elif entry_count >= 1:
            return 'Entry'
        else:
            return 'Mid'

    @staticmethod
    def detect_quantified_achievements(cv_data):
        """Phát hiện achievements được định lượng"""
        text_fields = [
            str(cv_data.get('job_description', '')),
            str(cv_data.get('project_description', '')),
        ]
        full_text = ' '.join(text_fields)
        
        achievement_patterns = [
            r'\d+%',
            r'\$\d+[KMB]?',
            r'\d+[KM]?\+?\s*(users|customers|clients|employees)',
            r'(increased|improved|reduced|grew|boosted|optimized)\s+\w+\s+by\s+\d+',
            r'\d+x\s+(faster|better|more)',
        ]
        
        score = 0
        for pattern in achievement_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            score += len(matches)
        
        return min(score, 10)

    @staticmethod
    def score_experience_quality(job_description, industry, seniority):
        """
        V2: Chấm điểm CHẤT LƯỢNG kinh nghiệm, không chỉ thời gian
        
        Returns: dict with breakdown
        """
        if pd.isna(job_description) or len(str(job_description).strip()) == 0:
            return {'total': 0, 'quantified': 0, 'leadership': 0, 'technical': 0}
        
        desc = str(job_description).lower()
        scores = {'total': 0, 'quantified': 0, 'leadership': 0, 'technical': 0}
        
        # 1. Quantified achievements (critical for all industries)
        achievement_keywords = [
            r'\d+%', r'\$\d+', r'increased', r'decreased', r'improved',
            r'grew', r'reduced', r'achieved', r'exceeded'
        ]
        quantified_count = sum(1 for pattern in achievement_keywords 
                               if re.search(pattern, desc, re.IGNORECASE))
        if quantified_count >= 3:
            scores['quantified'] = 15
        elif quantified_count >= 2:
            scores['quantified'] = 10
        elif quantified_count >= 1:
            scores['quantified'] = 5
        
        # 2. Leadership indicators (important for Mid+)
        if seniority in ['Mid', 'Senior', 'Lead']:
            leadership_keywords = ['led', 'managed', 'mentored', 'coached', 'supervised', 'directed']
            if any(kw in desc for kw in leadership_keywords):
                scores['leadership'] = 10 if seniority == 'Senior' else 5
        
        # 3. Industry-specific technical depth
        if industry in ['IT/Software', 'Data/AI', 'Security', 'QA/Testing']:
            tech_depth_keywords = [
                'architected', 'designed system', 'built from scratch',
                'optimized', 'refactored', 'implemented', 'deployed'
            ]
            tech_count = sum(1 for kw in tech_depth_keywords if kw in desc)
            scores['technical'] = min(tech_count * 3, 12)
        
        elif industry == 'Sales':
            sales_keywords = ['exceeded quota', 'top performer', 'closed deals', 'revenue']
            sales_count = sum(1 for kw in sales_keywords if kw in desc)
            scores['technical'] = min(sales_count * 5, 15)
        
        scores['total'] = sum(v for k, v in scores.items() if k != 'total')
        return scores

    @staticmethod
    def score_portfolio_links(links, industry):
        """
        V2: Enhanced portfolio scoring - industry-specific
        """
        if pd.isna(links) or len(str(links).strip()) == 0:
            return 0
        
        links_str = str(links).lower()
        score = 0
        
        if industry == 'Design':
            # Portfolio CRITICAL for design
            if 'behance.net' in links_str or 'dribbble.com' in links_str:
                score += 35  # Must-have!
            if 'portfolio' in links_str or 'website' in links_str:
                score += 20
            # NO PORTFOLIO = Major red flag (handled later)
        
        elif industry in ['IT/Software', 'Data/AI', 'Security']:
            # GitHub CRITICAL for tech
            if 'github.com' in links_str or 'gitlab.com' in links_str:
                score += 25
            if 'stackoverflow' in links_str:
                score += 5
            if 'kaggle' in links_str and industry == 'Data/AI':
                score += 10
        
        elif industry in ['Sales', 'Marketing', 'HR', 'Product']:
            # LinkedIn important
            if 'linkedin' in links_str:
                score += 10
        
        # Professional site always good
        if 'portfolio' in links_str or 'blog' in links_str or 'medium.com' in links_str:
            score += 5
        
        return min(score, 50)  # Max 50 for portfolio

    @staticmethod
    def detect_red_flags(cv_data, industry, seniority):
        """
        V2: Red flags detection - industry-specific
        Returns: (penalty_score, list_of_flags)
        """
        flags = []
        penalty = 0
        
        # 1. No quantified results (critical for Sales/Marketing)
        if industry in ['Sales', 'Marketing']:
            job_desc = str(cv_data.get('job_description', ''))
            if not re.search(r'\d+%|\$\d+|increased|improved', job_desc, re.IGNORECASE):
                flags.append("NO_QUANTIFIED_RESULTS")
                penalty += 20  # Major red flag
        
        # 2. No portfolio (CRITICAL for Design)
        if industry == 'Design':
            links = str(cv_data.get('links', ''))
            if not any(site in links.lower() for site in ['behance', 'dribbble', 'portfolio']):
                flags.append("NO_PORTFOLIO")
                penalty += 40  # Dealbreaker
        
        # 3. No GitHub (red flag for Mid+ developers)
        if industry in ['IT/Software', 'Data/AI'] and seniority in ['Mid', 'Senior']:
            links = str(cv_data.get('links', ''))
            if 'github' not in links.lower() and 'gitlab' not in links.lower():
                flags.append("NO_GITHUB_MID_SENIOR")
                penalty += 10
        
        # 4. No certifications (red flag for Finance/Security)
        if industry in ['Finance', 'Security']:
            certs = str(cv_data.get('certificates', ''))
            if len(certs.strip()) < 20:  # Very short or empty
                flags.append("NO_CERTIFICATIONS")
                penalty += 15
        
        # 5. Outdated tech stack (for IT)
        if industry == 'IT/Software':
            skills = str(cv_data.get('skills_list', '')).lower()
            outdated_tech = ['asp.net', 'vb.net', 'flash', 'silverlight', 'jquery mobile']
            modern_tech = ['react', 'vue', 'angular', 'docker', 'kubernetes', 'aws', 'azure']
            
            has_outdated = any(tech in skills for tech in outdated_tech)
            has_modern = any(tech in skills for tech in modern_tech)
            
            if has_outdated and not has_modern:
                flags.append("OUTDATED_TECH_STACK")
                penalty += 8
        
        return penalty, flags

    @staticmethod
    def calculate_weighted_score(base_scores, industry, seniority, student_status):
        """
        V2: Calculate score using DYNAMIC WEIGHTS theo ngành
        
        Args:
            base_scores: dict of raw scores from scoring functions
            industry: detected industry
            seniority: detected seniority level
            student_status: Student/Graduated/Unknown
        
        Returns:
            final_score (0-100), breakdown dict
        """
        
        # Get weights for this industry
        weights = INDUSTRY_WEIGHTS.get(industry, INDUSTRY_WEIGHTS['General'])
        
        # Normalize base scores to 0-100 scale
        normalized_scores = {
            'projects': (base_scores.get('projects', 0) / 35) * 100,
            'skills': (base_scores.get('skills', 0) / 20) * 100,
            'experience': (base_scores.get('experience', 0) / 30) * 100,
            'links': (base_scores.get('links', 0) / 50) * 100,  # New max 50
            'certificates': (base_scores.get('certificates', 0) / 15) * 100,
            'gpa': (base_scores.get('gpa', 0) / 10) * 100,
            'education': (base_scores.get('education', 0) / 10) * 100,
            'awards': (base_scores.get('awards', 0) / 15) * 100,
            'activities': (base_scores.get('activities', 0) / 7) * 100,
            'achievements': (base_scores.get('achievements', 0) / 10) * 100,
            'contact': (base_scores.get('contact', 0) / 5) * 100,
        }
        
        # Calculate weighted score
        weighted_score = 0
        for component, weight in weights.items():
            if component in normalized_scores:
                weighted_score += normalized_scores[component] * weight
        
        # Level adjustments
        if seniority == 'Entry' and student_status == 'Student':
            # Fresher: Boost projects, reduce experience requirement
            if industry in ['IT/Software', 'Data/AI']:
                if normalized_scores.get('projects', 0) >= 70:
                    weighted_score += 8
                if normalized_scores.get('experience', 0) < 30:
                    weighted_score += 5  # Not penalized for low experience
        
        elif seniority == 'Senior':
            # Senior: Require leadership and quantified results
            exp_quality = base_scores.get('exp_quality', {})
            if exp_quality.get('leadership', 0) >= 5:
                weighted_score += 5
            if exp_quality.get('quantified', 0) >= 10:
                weighted_score += 5
        
        # Red flags
        red_flag_penalty, flags = CVScoringRulesV2.detect_red_flags(
            {'links': base_scores.get('links_raw', ''),
             'job_description': base_scores.get('job_desc_raw', ''),
             'certificates': base_scores.get('certs_raw', ''),
             'skills_list': base_scores.get('skills_raw', '')},
            industry,
            seniority
        )
        
        final_score = max(0, min(100, weighted_score - red_flag_penalty))
        
        breakdown = {
            'weighted_score': weighted_score,
            'red_flag_penalty': red_flag_penalty,
            'red_flags': flags,
            'weights_used': weights,
            'normalized_scores': normalized_scores
        }
        
        return final_score, breakdown


# ============================================================================
# V2: MAIN SCORING FUNCTION
# ============================================================================

def score_cv_v2(cv_data):
    """
    V2: Main function để chấm điểm CV với dynamic weights
    
    Args:
        cv_data: dict from convert_read_cv4_to_dataframe()
    
    Returns:
        (final_score, detailed_breakdown)
    """
    
    # Detect industry and seniority
    industry, confidence = CVScoringRulesV2.detect_industry(cv_data)
    seniority = CVScoringRulesV2.detect_seniority(cv_data)
    student_status = detect_student_status(cv_data)
    
    # Import scoring functions from V1 (reuse)
    from thebrain import CVScoringRules
    
    # Calculate base scores
    base_scores = {
        'gpa': CVScoringRules.score_gpa(cv_data.get('gpa'), seniority),
        'education': CVScoringRules.score_education(cv_data.get('education_level')),
        'experience': CVScoringRules.score_experience(
            cv_data.get('job_description'),
            cv_data.get('start_date'),
            cv_data.get('end_date')
        ),
        'projects': CVScoringRules.score_projects(
            cv_data.get('project_name'),
            cv_data.get('project_description'),
            cv_data.get('project_technologies')
        ),
        'skills': CVScoringRules.score_skills(cv_data.get('skills_list')),
        'certificates': CVScoringRules.score_certificates(
            cv_data.get('certificates') if cv_data.get('certificates') else cv_data.get('activity_certificate')
        ),
        'awards': CVScoringRules.score_awards(
            cv_data.get('awards') if cv_data.get('awards') else cv_data.get('activity_certificate')
        ),
        'activities': CVScoringRules.score_activities(
            cv_data.get('activities') if cv_data.get('activities') else cv_data.get('activity_certificate')
        ),
        'contact': CVScoringRules.score_contact_info(cv_data.get('email'), cv_data.get('phone')),
        'achievements': CVScoringRulesV2.detect_quantified_achievements(cv_data),
        
        # V2: Enhanced scoring
        'links': CVScoringRulesV2.score_portfolio_links(cv_data.get('links'), industry),
        
        # Store raw data for red flags detection
        'links_raw': cv_data.get('links', ''),
        'job_desc_raw': cv_data.get('job_description', ''),
        'certs_raw': cv_data.get('certificates', ''),
        'skills_raw': cv_data.get('skills_list', ''),
    }
    
    # V2: Experience quality scoring
    exp_quality = CVScoringRulesV2.score_experience_quality(
        cv_data.get('job_description'),
        industry,
        seniority
    )
    base_scores['exp_quality'] = exp_quality
    
    # V2: Calculate weighted score
    final_score, breakdown = CVScoringRulesV2.calculate_weighted_score(
        base_scores,
        industry,
        seniority,
        student_status
    )
    
    # Add metadata
    breakdown['industry'] = industry
    breakdown['industry_confidence'] = confidence
    breakdown['seniority'] = seniority
    breakdown['student_status'] = student_status
    breakdown['base_scores'] = base_scores
    
    return final_score, breakdown


# ============================================================================
# V2: DISPLAY RESULTS
# ============================================================================

def display_cv_result_v2(pdf_path, target_job_level='Mid'):
    """Display kết quả với format mới"""
    
    print(f"\n{'='*70}")
    print(f"📄 Đang phân tích (V2): {os.path.basename(pdf_path)}")
    print(f"{'='*70}")
    
    # Bước 1: Đọc CV
    print("\n🔍 Bước 1: Đọc và trích xuất thông tin CV...")
    cv_text = extract_text_from_pdf(pdf_path)
    
    if not cv_text:
        print(f"❌ Không thể đọc file PDF")
        return None
    
    cv_info = extract_key_info(cv_text)
    cv_data = convert_read_cv4_to_dataframe(cv_info)
    print("   ✓ Trích xuất thành công")
    
    # Bước 2: Score CV V2
    print("\n🤖 Bước 2: AI V2 đang phân tích...")
    final_score, breakdown = score_cv_v2(cv_data)
    
    # Bước 3: Job match adjustment
    candidate_seniority = breakdown['seniority']
    match_adjustment = calculate_job_match_adjustment(candidate_seniority, target_job_level, final_score)
    adjusted_score = final_score + match_adjustment
    
    # Display results
    print("\n" + "="*70)
    print("📊 KẾT QUẢ PHÂN TÍCH V2 (DYNAMIC WEIGHTS)")
    print("="*70)
    
    print(f"\n🏢 NGÀNH NGHỀ: {breakdown['industry']} (confidence: {breakdown['industry_confidence']} keywords)")
    print(f"👤 CẤP BẬC ỨNG VIÊN: {breakdown['seniority']}")
    print(f"📚 TÌNH TRẠNG: {breakdown['student_status']}")
    print(f"🎯 VỊ TRÍ ỨNG TUYỂN: {target_job_level}")
    
    if match_adjustment > 0:
        print(f"✅ MATCH: Phù hợp (+{match_adjustment:.1f} điểm)")
    elif match_adjustment < 0:
        print(f"⚠️  MISMATCH: Không phù hợp ({match_adjustment:.1f} điểm)")
    
    # Red flags
    if breakdown['red_flags']:
        print(f"\n🚩 RED FLAGS:")
        for flag in breakdown['red_flags']:
            print(f"   ❌ {flag}")
        print(f"   Penalty: -{breakdown['red_flag_penalty']} điểm")
    
    # Weights used
    print(f"\n📊 TRỌNG SỐ SỬ DỤNG CHO {breakdown['industry'].upper()}:")
    for component, weight in breakdown['weights_used'].items():
        if weight > 0:
            print(f"   • {component.title()}: {weight*100:.0f}%")
    
    # Component scores
    print(f"\n📈 CHI TIẾT ĐIỂM SỐ:")
    base_scores = breakdown['base_scores']
    normalized = breakdown['normalized_scores']
    
    important_components = sorted(
        breakdown['weights_used'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:6]
    
    for component, weight in important_components:
        if component in normalized:
            raw_score = base_scores.get(component, 0)
            norm_score = normalized[component]
            bar_length = int(norm_score / 100 * 30)
            bar = '█' * bar_length + '░' * (30 - bar_length)
            print(f"   {component.title():.<20} {bar} {norm_score:>5.1f}% (weight: {weight*100:.0f}%)")
    
    # Experience quality breakdown
    if 'exp_quality' in base_scores:
        exp_q = base_scores['exp_quality']
        print(f"\n   💼 Experience Quality Breakdown:")
        print(f"      • Quantified results: {exp_q['quantified']}/15")
        print(f"      • Leadership: {exp_q['leadership']}/10")
        print(f"      • Technical depth: {exp_q['technical']}/12")
    
    # Final score
    print("\n" + "="*70)
    print(f"   📊 ĐIỂM BASE (V2 Weighted): {final_score:.2f}/100")
    if match_adjustment != 0:
        print(f"   🎯 ĐIỂM MATCH (Job Level): {match_adjustment:+.2f}")
        print(f"   🎯 ĐIỂM CUỐI CÙNG: {adjusted_score:.2f}/100")
    else:
        print(f"   🎯 ĐIỂM CUỐI CÙNG: {final_score:.2f}/100")
    
    percentage = adjusted_score if match_adjustment != 0 else final_score
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
        'final_score': final_score,
        'adjusted_score': adjusted_score,
        'grade': grade,
        'breakdown': breakdown
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='THE BRAIN V2 - AI Chấm Điểm CV (Dynamic Weights)',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('files', nargs='+', help='File PDF CV cần chấm điểm')
    parser.add_argument('--job-level', '--level', '-l', 
                       choices=['Intern', 'Entry', 'Mid', 'Senior', 'Lead'],
                       default='Mid',
                       help='Vị trí ứng tuyển (default: Mid)')
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("🧠 THE BRAIN V2 - AI Chấm Điểm CV (DYNAMIC WEIGHTS)")
    print("="*80)
    
    # Get PDF files
    pdf_files = []
    for pattern in args.files:
        if '*' in pattern or '?' in pattern:
            pdf_files.extend(glob.glob(pattern))
        else:
            pdf_files.append(pattern)
    
    pdf_files = [f for f in pdf_files if f.lower().endswith('.pdf') and os.path.exists(f)]
    
    if not pdf_files:
        print("❌ Không tìm thấy file PDF nào!")
        return
    
    print(f"\n📂 Tìm thấy {len(pdf_files)} file PDF")
    print(f"🎯 Vị trí ứng tuyển: {args.job_level}")
    
    # Score each CV
    results = []
    for pdf_file in pdf_files:
        result = display_cv_result_v2(pdf_file, args.job_level)
        if result:
            results.append(result)
    
    # Summary
    if len(results) > 1:
        print("\n" + "="*80)
        print("📊 BẢNG TỔNG HỢP")
        print("="*80 + "\n")
        
        results.sort(key=lambda x: x['adjusted_score'], reverse=True)
        
        print(f"{'STT':<5} {'TÊN FILE':<30} {'V2 SCORE':<12} {'LOẠI':<15}")
        print("-"*80)
        
        for idx, result in enumerate(results, 1):
            fname = result['file_name']
            if len(fname) > 28:
                fname = fname[:25] + "..."
            
            print(f"{idx:<5} {fname:<30} {result['adjusted_score']:>6.2f}/100  {result['grade']:<15}")
        
        print("="*80 + "\n")


if __name__ == "__main__":
    main()
