"""
Example plugin demonstrating the CSV Visualizer plugin API.

Drop this file into the plugins/ directory to activate it.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.plugin_service import Plugin


def _data_quality_insights(df):
    """Generate data quality insights."""
    insights = []

    # Check for constant columns (zero variance)
    for col in df.columns:
        if df[col].nunique() == 1:
            insights.append({
                'type': 'data_quality',
                'icon': 'alert-triangle',
                'severity': 'warning',
                'title': f'Constant column: {col}',
                'detail': f'Column "{col}" has only one unique value and may not be useful for analysis.',
            })

    # Check for columns that are mostly empty
    for col in df.columns:
        null_pct = df[col].isnull().mean()
        if null_pct > 0.5:
            insights.append({
                'type': 'data_quality',
                'icon': 'alert-triangle',
                'severity': 'warning',
                'title': f'Sparse column: {col}',
                'detail': f'Column "{col}" is {null_pct:.0%} empty.',
            })

    return insights


def create_plugin():
    """Factory function called by the plugin loader."""
    return Plugin(
        name='data-quality',
        version='1.0.0',
        description='Detects data quality issues like constant columns and sparse data',
        author='CSV Visualizer',
        hooks={
            'insight_generator': _data_quality_insights,
        },
    )
