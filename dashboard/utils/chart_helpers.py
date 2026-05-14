import plotly.express as px
import pandas as pd


def equity_bar(df: pd.DataFrame, x: str, y: str, title: str):
    """Bar chart with a reference line at equity_score = 1.0."""
    fig = px.bar(df, x=x, y=y, title=title, color=x, color_continuous_scale="RdYlGn_r")
    fig.add_hline(y=1.0, line_dash="dash", line_color="grey", annotation_text="City average")
    fig.update_layout(showlegend=False)
    return fig


def scatter_income_vs_wait(df: pd.DataFrame):
    return px.scatter(
        df,
        x="median_household_income",
        y="p90_hours",
        color="borough",
        size="complaint_count",
        hover_data=["tract_geoid", "complaint_type", "equity_score"],
        labels={"median_household_income": "Median Household Income ($)", "p90_hours": "P90 Response (hrs)"},
        title="Income vs. P90 Response Time by Tract",
        opacity=0.6,
    )


def complaint_heatmap(df: pd.DataFrame, value_col: str):
    pivot = df.pivot_table(index="complaint_type", columns="borough", values=value_col, aggfunc="mean")
    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale="RdYlGn_r",
        title=f"{value_col} by Complaint Type and Borough",
        labels={"color": value_col},
    )
    return fig
