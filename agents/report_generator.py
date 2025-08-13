import os
import logging
import pandas as pd
from typing import Dict, List, Optional
from groq import Groq
from jinja2 import Template
import json
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import base64
import io

logger = logging.getLogger(__name__)

class ReportGeneratorAgent:
    def __init__(self, groq_api_key: str):
        self.groq_client = Groq(api_key=groq_api_key)
        self.logger = logging.getLogger(__name__)
        self.report_data = None
        self.generated_charts = []
        self.search_context: Dict = {}
    
    def generate_report(self, cleaned_data: pd.DataFrame, report_format: Dict, context: Dict = None) -> str:
        try:
            self.logger.info("Starting report generation")
            
            self.report_data = cleaned_data
            self.search_context = context or {}
            
            # No charts/images in reports
            # Force-disable chart generation regardless of input flag
            # This ensures fully text-only reports
            self.generated_charts = []
            
            ai_analysis = self._generate_ai_analysis(cleaned_data)
            summary_stats = self._generate_summary_statistics(cleaned_data)
            
            report_content = self._create_report(
                cleaned_data, 
                ai_analysis, 
                summary_stats, 
                report_format
            )
            
            self.logger.info("Report generation completed")
            return report_content
            
        except Exception as e:
            self.logger.error(f"Error in report generation: {e}")
            raise
    
    def _generate_ai_analysis(self, data: pd.DataFrame) -> Dict:
        try:
            self.logger.info("Generating AI analysis using LLaMA 4")
            
            if data.empty:
                return {
                    'key_insights': ['No data available for analysis'],
                    'trends': [],
                    'recommendations': []
                }
            
            data_summary = self._prepare_data_summary(data)
            
            prompt = self._create_analysis_prompt(data_summary, data)
            
            response = self.groq_client.chat.completions.create(
                model="meta-llama/llama-4-maverick-17b-128e-instruct",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert analyst. Write a clear, human-readable, well-structured text-only report. "
                            "No images. No tables. Base insights strictly on provided data; avoid speculation. "
                            "Be concise, factual, and organized."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=900,
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            
            try:
                analysis = json.loads(content)
                return analysis
            except json.JSONDecodeError:
                return self._parse_ai_response_manually(content)
                
        except Exception as e:
            self.logger.error(f"Error in AI analysis: {e}")
            return {
                'key_insights': ['Unable to generate AI analysis due to technical issues'],
                'trends': [],
                'recommendations': []
            }
    
    def _prepare_data_summary(self, data: pd.DataFrame) -> Dict:
        summary = {
            'total_records': len(data),
            'columns': list(data.columns),
            'data_types': data.dtypes.to_dict()
        }
        
        if 'location' in data.columns:
            summary['top_locations'] = data['location'].value_counts().head(5).to_dict()
        
        if 'all_skills' in data.columns:
            summary['common_skills'] = self._get_common_skills(data)
            summary['avg_skills_per_record'] = data['all_skills'].apply(len).mean()
        
        if 'experience' in data.columns:
            summary['records_with_experience'] = len(data[data['experience'].apply(len) > 0])
        
        if 'source' in data.columns:
            summary['sources'] = data['source'].value_counts().to_dict()
        
        return summary
    
    def _create_analysis_prompt(self, data_summary: Dict, data: pd.DataFrame) -> str:
        answer = (self.search_context.get('search_answer') or
                  self.search_context.get('answer') or '')
        sources = self.search_context.get('sources', [])
        user_query = self.search_context.get('user_input', '')
        prompt = f"""
        Task: Draft an Executive Summary and 4-6 bullet Key Findings for a factual, text-only report.
        Base your analysis strictly on the dataset and the search answer below; avoid speculation.

        User Query: {user_query}
        Search Answer (if any): {answer}
        Sources: {sources}

        Dataset Summary:
        - Total records: {data_summary['total_records']}
        - Columns: {data_summary['columns']}
        - Data types: {data_summary['data_types']}

        Sample data (first 3 records):
        {data.head(3).to_dict('records')}

        Return JSON with exactly these keys:
        {{
            "key_insights": ["...", "..."],
            "trends": [],
            "recommendations": []
        }}
        """
        return prompt
    
    def _parse_ai_response_manually(self, content: str) -> Dict:
        insights = []
        trends = []
        recommendations = []
        
        lines = content.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if 'insight' in line.lower() or 'key' in line.lower():
                current_section = 'insights'
            elif 'trend' in line.lower():
                current_section = 'trends'
            elif 'recommendation' in line.lower() or 'suggestion' in line.lower():
                current_section = 'recommendations'
            elif line.startswith('-') or line.startswith('•') or line.startswith('*'):
                item = line[1:].strip()
                if current_section == 'insights':
                    insights.append(item)
                elif current_section == 'trends':
                    trends.append(item)
                elif current_section == 'recommendations':
                    recommendations.append(item)
        
        return {
            'key_insights': insights[:3] if insights else ['Data analysis completed'],
            'trends': trends[:2] if trends else ['No specific trends identified'],
            'recommendations': recommendations[:2] if recommendations else ['Consider expanding your search criteria']
        }
    
    def _generate_summary_statistics(self, data: pd.DataFrame) -> Dict:
        try:
            if data.empty:
                return {
                    'total_records': 0,
                    'unique_locations': 0,
                    'records_with_skills': 0,
                    'records_with_experience': 0,
                    'avg_skills_per_record': 0,
                    'top_locations': {},
                    'source_distribution': {},
                    'experience_levels': {}
                }
            
            stats = {
                'total_records': len(data),
                'unique_locations': data['location'].nunique() if 'location' in data.columns else 0,
                'records_with_skills': len(data[data['all_skills'].apply(len) > 0]) if 'all_skills' in data.columns else 0,
                'records_with_experience': len(data[data['experience'].apply(len) > 0]) if 'experience' in data.columns else 0,
                'avg_skills_per_record': data['all_skills'].apply(len).mean() if 'all_skills' in data.columns else 0,
                'top_locations': data['location'].value_counts().head(10).to_dict() if 'location' in data.columns else {},
                'source_distribution': data['source'].value_counts().to_dict() if 'source' in data.columns else {},
                'experience_levels': self._analyze_experience_levels(data)
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error generating summary statistics: {e}")
            return {
                'total_records': 0,
                'unique_locations': 0,
                'records_with_skills': 0,
                'records_with_experience': 0,
                'avg_skills_per_record': 0,
                'top_locations': {},
                'source_distribution': {},
                'experience_levels': {}
            }
    
    def _get_common_skills(self, data: pd.DataFrame, top_n: int = 10) -> Dict:
        try:
            if data.empty or 'all_skills' not in data.columns:
                return {}
            
            all_skills = []
            for skills_list in data['all_skills']:
                if isinstance(skills_list, list):
                    all_skills.extend(skills_list)
            
            if not all_skills:
                return {}
            
            skill_counts = {}
            for skill in all_skills:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
            
            sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
            return dict(sorted_skills[:top_n])
            
        except Exception as e:
            self.logger.error(f"Error getting common skills: {e}")
            return {}
    
    def _analyze_experience_levels(self, data: pd.DataFrame) -> Dict:
        try:
            if data.empty:
                return {'entry': 0, 'mid': 0, 'senior': 0, 'executive': 0, 'unknown': 0}
            
            levels = {'entry': 0, 'mid': 0, 'senior': 0, 'executive': 0, 'unknown': 0}
            
            if 'headline' in data.columns:
                for headline in data['headline']:
                    if isinstance(headline, str):
                        headline_lower = headline.lower()
                        if any(word in headline_lower for word in ['senior', 'lead', 'principal']):
                            levels['senior'] += 1
                        elif any(word in headline_lower for word in ['junior', 'entry', 'associate']):
                            levels['entry'] += 1
                        elif any(word in headline_lower for word in ['director', 'vp', 'cto', 'ceo']):
                            levels['executive'] += 1
                        elif any(word in headline_lower for word in ['engineer', 'developer', 'analyst']):
                            levels['mid'] += 1
                        else:
                            levels['unknown'] += 1
            
            return levels
            
        except Exception as e:
            self.logger.error(f"Error analyzing experience levels: {e}")
            return {'entry': 0, 'mid': 0, 'senior': 0, 'executive': 0, 'unknown': 0}
    
    def _generate_charts(self):
        # Charts disabled by requirement: no images in the report
        self.generated_charts = []
    
    def _generate_location_chart(self):
        try:
            location_counts = self.report_data['location'].value_counts().head(10)
            
            plt.figure(figsize=(10, 6))
            location_counts.plot(kind='bar')
            plt.title('Top Locations')
            plt.xlabel('Location')
            plt.ylabel('Count')
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
            img_buffer.seek(0)
            
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
            self.generated_charts.append({
                'title': 'Top Locations',
                'type': 'bar',
                'data': img_base64
            })
            
            plt.close()
            
        except Exception as e:
            self.logger.error(f"Error generating location chart: {e}")
    
    def _generate_skills_chart(self):
        try:
            all_skills = []
            for skills_list in self.report_data['all_skills']:
                if isinstance(skills_list, list):
                    all_skills.extend(skills_list)
            
            if not all_skills:
                return
            
            skill_counts = {}
            for skill in all_skills:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
            
            top_skills = dict(sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:10])
            
            plt.figure(figsize=(12, 6))
            plt.bar(top_skills.keys(), top_skills.values())
            plt.title('Top Skills')
            plt.xlabel('Skill')
            plt.ylabel('Count')
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
            img_buffer.seek(0)
            
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
            self.generated_charts.append({
                'title': 'Top Skills',
                'type': 'bar',
                'data': img_base64
            })
            
            plt.close()
            
        except Exception as e:
            self.logger.error(f"Error generating skills chart: {e}")
    
    def _generate_source_chart(self):
        try:
            source_counts = self.report_data['source'].value_counts()
            
            plt.figure(figsize=(8, 8))
            plt.pie(source_counts.values, labels=source_counts.index, autopct='%1.1f%%')
            plt.title('Data Sources Distribution')
            plt.axis('equal')
            
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
            img_buffer.seek(0)
            
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
            self.generated_charts.append({
                'title': 'Data Sources Distribution',
                'type': 'pie',
                'data': img_base64
            })
            
            plt.close()
            
        except Exception as e:
            self.logger.error(f"Error generating source chart: {e}")
    
    def _create_report(self, data: pd.DataFrame, ai_analysis: Dict, summary_stats: Dict, report_format: Dict) -> str:
        try:
            template_content = self._get_report_template()
            template = Template(template_content)
            
            # Derive view-specific rows
            sample_records = data.head(8).to_dict('records') if not data.empty else []
            has_linkedin = any((r.get('source') or '').lower() == 'linkedin' for r in sample_records)
            li_rows = [
                {
                    'name': r.get('name') or 'N/A',
                    'headline': r.get('headline') or 'N/A',
                    'location': r.get('location') or 'N/A',
                    'source': r.get('source') or 'N/A'
                }
                for r in sample_records if (r.get('source') or '').lower() == 'linkedin'
            ]
            web_rows = [
                {
                    'title': r.get('name') or r.get('profile_url') or 'N/A',
                    'snippet': (r.get('summary') or '')[:220],
                    'url': r.get('profile_url') or ''
                }
                for r in sample_records if (r.get('source') or '').lower() != 'linkedin'
            ]

            report_data = {
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_records': len(data),
                'ai_analysis': ai_analysis,
                'summary_stats': summary_stats,
                'charts': self.generated_charts,
                'sample_data': sample_records,
                'report_format': report_format,
                'user_input': self.search_context.get('user_input', ''),
                'sources': self.search_context.get('sources', []),
                'linkedin_profiles': self.search_context.get('linkedin_profiles', []),
                'direct_answer': self.search_context.get('answer', '') or self.search_context.get('search_answer', ''),
                'has_linkedin': has_linkedin,
                'li_rows': li_rows,
                'web_rows': web_rows
            }
            
            report_content = template.render(**report_data)
            return report_content
            
        except Exception as e:
            self.logger.error(f"Error creating report: {e}")
            return f"Error generating report: {str(e)}"
    
    def _get_report_template(self) -> str:
        return """
Generated on: {{ generated_at }}

---

# Research Report

---

## 1. Query Context & Objective

- User Query: {{ user_input if user_input else 'N/A' }}
- Interpreted Objective: Provide a concise, factual answer supported by reputable sources and profile evidence where available.
- Timeframe: Current
- Intended Output Type: Analysis report

---

## 2. Executive Summary

{% if direct_answer %}
{{ direct_answer }}
{% elif ai_analysis.key_insights %}
{% for insight in ai_analysis.key_insights %}
- {{ insight }}
{% endfor %}
{% else %}
- No executive insights available.
{% endif %}

---

{% if has_linkedin %}
## 3A. Core Data – LinkedIn Profiles

| Name | Headline | Location | Source |
|------|----------|----------|--------|
{% for r in li_rows %}
| {{ r.name }} | {{ r.headline }} | {{ r.location }} | {{ r.source }} |
{% endfor %}

{% endif %}

## {% if has_linkedin %}3B{% else %}3{% endif %}. Core Data – Web Sources

| Title/URL | Snippet |
|-----------|---------|
{% for w in web_rows %}
| {{ w.title }} | {{ w.snippet }} |
{% endfor %}

---

## 4. Sources
{% if sources and sources|length > 0 %}
{% for u in sources %}
- {{ u }}
{% endfor %}
{% else %}
- N/A
{% endif %}

---
Report generated by AI Agent System
"""
