import pandas as pd
df = pd.read_csv("benchmark/ppbench_results/task_3/plotly/data.csv")

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

df = pd.read_csv("benchmark/ppbench_results/task_3/plotly/data.csv")

# Reshape first two columns into 2x2 matrices
col_a_matrix = df['a'].values.reshape(2, 2)
col_b_matrix = df['b'].values.reshape(2, 2)

# Create subplot with 2x2 grid
fig = make_subplots(
    rows=2, cols=2,
    subplot_titles=['Column A - Position (1,1)', 'Column A - Position (1,2)', 
                   'Column B - Position (2,1)', 'Column B - Position (2,2)'],
    horizontal_spacing=0.15,
    vertical_spacing=0.15
)

# Add heatmaps for column A matrices
fig.add_trace(
    go.Heatmap(z=col_a_matrix, showscale=False, colorscale='Blues'),
    row=1, col=1
)

fig.add_trace(
    go.Heatmap(z=col_a_matrix, showscale=False, colorscale='Blues'),
    row=1, col=2
)

# Add heatmaps for column B matrices
fig.add_trace(
    go.Heatmap(z=col_b_matrix, showscale=False, colorscale='Reds'),
    row=2, col=1
)

fig.add_trace(
    go.Heatmap(z=col_b_matrix, showscale=False, colorscale='Reds'),
    row=2, col=2
)

# Update layout for consistent axis scales and aspect ratios
fig.update_layout(
    title="2x2 Grid Layout of Reshaped DataFrame Columns",
    height=600,
    width=600
)

# Update all subplots to have consistent axis settings
for i in range(1, 3):
    for j in range(1, 3):
        fig.update_xaxes(range=[-0.5, 1.5], row=i, col=j)
        fig.update_yaxes(range=[-0.5, 1.5], row=i, col=j)

fig.write_image("/Users/dawid.olejniczak/Documents/GitHub/playground/benchmark/ppbench_results/task_3/plotly/output.png")