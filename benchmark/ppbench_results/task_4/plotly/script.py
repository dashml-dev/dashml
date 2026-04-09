import pandas as pd
df = pd.read_csv("benchmark/ppbench_results/task_4/plotly/data.csv")

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

df = pd.read_csv("benchmark/ppbench_results/task_4/plotly/data.csv")

fig = make_subplots(
    rows=2, cols=2,
    subplot_titles=['A', 'B', 'C', 'D'],
    vertical_spacing=0.15,
    horizontal_spacing=0.1
)

columns = ['A', 'B', 'C', 'D']
positions = [(1, 1), (1, 2), (2, 1), (2, 2)]

for i, (col, pos) in enumerate(zip(columns, positions)):
    row, col_pos = pos
    
    # Main line plot
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df[col],
            mode='lines',
            line=dict(color='blue', width=2),
            name=f'{col}_main',
            showlegend=False
        ),
        row=row, col=col_pos
    )
    
    # Inset data (focusing on middle portion of data)
    start_idx = len(df) // 4
    end_idx = 3 * len(df) // 4
    inset_x = df.index[start_idx:end_idx]
    inset_y = df[col].iloc[start_idx:end_idx]
    
    # Add inset as a separate trace with different color
    fig.add_trace(
        go.Scatter(
            x=inset_x,
            y=inset_y,
            mode='lines',
            line=dict(color='red', width=3),
            name=f'{col}_inset',
            showlegend=False
        ),
        row=row, col=col_pos
    )

fig.update_layout(
    title="Line Plots with Insets for Each Column",
    height=600,
    width=800,
    showlegend=False
)

fig.update_xaxes(title_text="Index")
fig.update_yaxes(title_text="Value")

fig.write_image("/Users/dawid.olejniczak/Documents/GitHub/playground/benchmark/ppbench_results/task_4/plotly/output.png")