import plotly.express as px
import pandas as pd


def equity_bar(df: pd.DataFrame, x: str, y: str, title: str):
    """Bar chart with a reference line at equity_score = 1.0."""
    fig = px.bar(df, x=x, y=y, title=title, color=x, color_continuous_scale="RdYlGn_r")
    fig.add_hline(y=1.0, line_dash="dash", line_color="grey", annotation_text="City average")
    fig.update_layout(showlegend=False)
    return fig


def scatter_income_vs_wait(df: pd.DataFrame):
    import numpy as np

    fig = px.scatter(
        df,
        x="median_household_income",
        y="p90_hours",
        color="borough",
        size="complaint_count",
        hover_data=["tract_geoid", "complaint_type", "equity_score"],
        labels={"median_household_income": "Median Household Income ($)", "p90_hours": "P90 Response (hrs)"},
        title="Income vs. P90 Response Time by Tract",
        opacity=0.25,  # low opacity turns overlapping dots into a density map
    )

    # OLS trend line across all tracts regardless of borough
    valid = df.dropna(subset=["median_household_income", "p90_hours"])
    if len(valid) > 1:
        x = valid["median_household_income"].values
        y = valid["p90_hours"].values
        m, b = np.polyfit(x, y, 1)
        x_range = np.linspace(x.min(), x.max(), 200)
        fig.add_scatter(
            x=x_range,
            y=m * x_range + b,
            mode="lines",
            line={"color": "white", "width": 2, "dash": "dash"},
            name="Trend",
            showlegend=True,
        )

    return fig


def complaint_heatmap(df: pd.DataFrame, value_col: str):
    pivot = df.pivot_table(index="complaint_type", columns="borough", values=value_col, aggfunc="mean")
    # 30px per row so all complaint types are visible without zooming
    height = max(500, len(pivot) * 30)
    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale="RdYlGn_r",
        title=f"{value_col} by Complaint Type and Borough",
        labels={"color": value_col},
        height=height,
    )
    fig.update_layout(
        yaxis={"tickfont": {"size": 11}},
        xaxis={"tickfont": {"size": 12}},
    )
    return fig
