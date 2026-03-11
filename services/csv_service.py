import pandas as pd
import numpy as np
from pathlib import Path


def parse_csv(filepath, nrows=None):
    """Parse a CSV file and return a DataFrame with metadata."""
    path = Path(filepath)
    sep = '\t' if path.suffix == '.tsv' else ','
    df = pd.read_csv(filepath, sep=sep, nrows=nrows, encoding_errors='replace')
    return df


def get_column_info(df):
    """Classify columns by type for smart chart suggestions."""
    info = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        nunique = df[col].nunique()
        null_pct = round(df[col].isnull().mean() * 100, 1)
        sample = df[col].dropna().head(3).tolist()

        if pd.api.types.is_numeric_dtype(df[col]):
            col_type = 'numeric'
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            col_type = 'temporal'
        else:
            parsed = pd.to_datetime(df[col], errors='coerce', format='mixed')
            if parsed.notna().mean() > 0.8:
                col_type = 'temporal'
            elif nunique <= 20 or (nunique / max(len(df), 1)) < 0.05:
                col_type = 'categorical'
            else:
                col_type = 'text'

        info.append({
            'name': col,
            'dtype': dtype,
            'col_type': col_type,
            'nunique': int(nunique),
            'null_pct': null_pct,
            'sample': [str(s) for s in sample],
        })
    return info


def generate_insights(df):
    """Auto-detect interesting patterns in the data."""
    insights = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    # Dataset overview
    insights.append({
        'type': 'overview',
        'icon': 'table',
        'title': 'Dataset Shape',
        'detail': f'{len(df):,} rows x {len(df.columns)} columns',
        'severity': 'info',
    })

    # Missing data
    total_missing = df.isnull().sum().sum()
    if total_missing > 0:
        worst_col = df.isnull().sum().idxmax()
        worst_pct = round(df[worst_col].isnull().mean() * 100, 1)
        insights.append({
            'type': 'missing',
            'icon': 'alert-triangle',
            'title': 'Missing Values',
            'detail': f'{total_missing:,} missing cells. Worst: "{worst_col}" ({worst_pct}% null)',
            'severity': 'warning' if worst_pct > 20 else 'info',
        })

    # Outliers (IQR method) on numeric columns
    for col in numeric_cols[:10]:
        series = df[col].dropna()
        if len(series) < 10:
            continue
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = series[(series < lower) | (series > upper)]
        if len(outliers) > 0:
            pct = round(len(outliers) / len(series) * 100, 1)
            insights.append({
                'type': 'outlier',
                'icon': 'zap',
                'title': f'Outliers in "{col}"',
                'detail': f'{len(outliers)} outlier(s) ({pct}%) outside [{lower:.2f}, {upper:.2f}]',
                'severity': 'warning' if pct > 5 else 'info',
            })

    # Strong correlations
    if len(numeric_cols) >= 2:
        try:
            corr = df[numeric_cols].corr()
            for i in range(len(numeric_cols)):
                for j in range(i + 1, len(numeric_cols)):
                    r = corr.iloc[i, j]
                    if abs(r) > 0.7 and not np.isnan(r):
                        direction = 'positive' if r > 0 else 'negative'
                        insights.append({
                            'type': 'correlation',
                            'icon': 'trending-up' if r > 0 else 'trending-down',
                            'title': f'Strong Correlation',
                            'detail': f'"{numeric_cols[i]}" & "{numeric_cols[j]}": r={r:.3f} ({direction})',
                            'severity': 'success',
                            'columns': [numeric_cols[i], numeric_cols[j]],
                        })
        except Exception:
            pass

    # Skewed distributions
    for col in numeric_cols[:10]:
        series = df[col].dropna()
        if len(series) < 20:
            continue
        try:
            skew = series.skew()
            if abs(skew) > 2:
                direction = 'right' if skew > 0 else 'left'
                insights.append({
                    'type': 'skew',
                    'icon': 'bar-chart-2',
                    'title': f'Skewed: "{col}"',
                    'detail': f'Heavily {direction}-skewed (skewness={skew:.2f}). Consider log transform.',
                    'severity': 'info',
                })
        except Exception:
            pass

    # High cardinality warning
    for col in df.columns:
        if df[col].dtype == 'object' and df[col].nunique() > 100:
            insights.append({
                'type': 'cardinality',
                'icon': 'hash',
                'title': f'High Cardinality: "{col}"',
                'detail': f'{df[col].nunique()} unique values — likely an ID or free-text column',
                'severity': 'info',
            })

    # Duplicate rows
    dup_count = df.duplicated().sum()
    if dup_count > 0:
        insights.append({
            'type': 'duplicates',
            'icon': 'copy',
            'title': 'Duplicate Rows',
            'detail': f'{dup_count} duplicate row(s) found ({round(dup_count / len(df) * 100, 1)}%)',
            'severity': 'warning',
        })

    # Sort: warnings first, then info
    severity_order = {'warning': 0, 'success': 1, 'info': 2}
    insights.sort(key=lambda x: severity_order.get(x['severity'], 3))

    return insights


def suggest_charts(df, column_info):
    """Generate chart configs based on column types."""
    charts = []
    numeric_cols = [c for c in column_info if c['col_type'] == 'numeric']
    categorical_cols = [c for c in column_info if c['col_type'] == 'categorical']
    temporal_cols = [c for c in column_info if c['col_type'] == 'temporal']

    # Histogram for first numeric column
    if numeric_cols:
        col = numeric_cols[0]['name']
        charts.append({
            'id': f'hist_{col}',
            'type': 'histogram',
            'title': f'Distribution of {col}',
            'x': col,
            'data': df[col].dropna().tolist()[:5000],
        })

    # Scatter plot for first two numeric columns
    if len(numeric_cols) >= 2:
        c1, c2 = numeric_cols[0]['name'], numeric_cols[1]['name']
        subset = df[[c1, c2]].dropna().head(5000)
        charts.append({
            'id': f'scatter_{c1}_{c2}',
            'type': 'scatter',
            'title': f'{c1} vs {c2}',
            'x': c1,
            'y': c2,
            'data_x': subset[c1].tolist(),
            'data_y': subset[c2].tolist(),
        })

    # Bar chart for categorical + numeric
    if categorical_cols and numeric_cols:
        cat_col = categorical_cols[0]['name']
        num_col = numeric_cols[0]['name']
        agg = df.groupby(cat_col)[num_col].mean().sort_values(ascending=False).head(20)
        charts.append({
            'id': f'bar_{cat_col}_{num_col}',
            'type': 'bar',
            'title': f'Mean {num_col} by {cat_col}',
            'x': agg.index.astype(str).tolist(),
            'y': agg.values.tolist(),
            'x_label': cat_col,
            'y_label': num_col,
        })

    # Box plots for numeric columns (up to 6)
    if len(numeric_cols) >= 2:
        box_cols = [c['name'] for c in numeric_cols[:6]]
        box_data = []
        for col in box_cols:
            vals = df[col].dropna().tolist()[:5000]
            box_data.append({'name': col, 'values': vals})
        charts.append({
            'id': 'box_comparison',
            'type': 'box',
            'title': 'Numeric Column Distributions',
            'data': box_data,
        })

    # Time series if temporal column found
    if temporal_cols and numeric_cols:
        t_col = temporal_cols[0]['name']
        n_col = numeric_cols[0]['name']
        try:
            ts_df = df[[t_col, n_col]].dropna().copy()
            ts_df[t_col] = pd.to_datetime(ts_df[t_col], errors='coerce')
            ts_df = ts_df.dropna().sort_values(t_col).head(5000)
            charts.append({
                'id': f'timeseries_{t_col}_{n_col}',
                'type': 'timeseries',
                'title': f'{n_col} over {t_col}',
                'x': ts_df[t_col].astype(str).tolist(),
                'y': ts_df[n_col].tolist(),
                'x_label': t_col,
                'y_label': n_col,
            })
        except Exception:
            pass

    # Correlation heatmap
    if len(numeric_cols) >= 3:
        cols = [c['name'] for c in numeric_cols[:12]]
        corr = df[cols].corr()
        charts.append({
            'id': 'correlation_heatmap',
            'type': 'heatmap',
            'title': 'Correlation Matrix',
            'labels': cols,
            'values': corr.values.tolist(),
        })

    return charts


def get_summary_stats(df):
    """Return summary statistics as a serializable dict."""
    stats = {}
    for col in df.columns:
        col_stats = {'name': col, 'dtype': str(df[col].dtype), 'count': int(df[col].count())}
        if pd.api.types.is_numeric_dtype(df[col]):
            desc = df[col].describe()
            col_stats.update({
                'mean': round(float(desc['mean']), 4) if not np.isnan(desc['mean']) else None,
                'std': round(float(desc['std']), 4) if not np.isnan(desc['std']) else None,
                'min': float(desc['min']),
                'max': float(desc['max']),
                'median': round(float(df[col].median()), 4),
            })
        else:
            col_stats.update({
                'unique': int(df[col].nunique()),
                'top': str(df[col].mode().iloc[0]) if not df[col].mode().empty else None,
            })
        stats[col] = col_stats
    return stats
