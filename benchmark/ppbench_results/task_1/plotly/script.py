import pandas as pd
df = pd.read_csv("benchmark/ppbench_results/task_1/plotly/data.csv")

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

df = pd.read_csv("benchmark/ppbench_results/task_1/plotly/data.csv")

# Create a pivot table to get matrix format
matrix = df.pivot(index='y', columns='x', values='z')

# Fill any missing values with 0
matrix = matrix.fillna(0)

# Create subplots
fig = make_subplots(
    rows=1, cols=2,
    subplot_titles=('Matrix Plot 1', 'Matrix Plot 2'),
    horizontal_spacing=0.15
)

# First subplot with horizontal colorbar on top
fig.add_trace(
    go.Heatmap(
        z=matrix.values,
        x=matrix.columns,
        y=matrix.index,
        colorscale='Viridis',
        showscale=True,
        colorbar=dict(
            orientation="h",
            x=0.45,
            y=1.1,
            len=0.4,
            thickness=15
        )
    ),
    row=1, col=1
)

# Second subplot with vertical colorbar on right
fig.add_trace(
    go.Heatmap(
        z=matrix.values,
        x=matrix.columns,
        y=matrix.index,
        colorscale='Plasma',
        showscale=True,
        colorbar=dict(
            orientation="v",
            x=1.02,
            y=0.5,
            len=0.8,
            thickness=15
        )
    ),
    row=1, col=2
)

# Update layout
fig.update_layout(
    title="Matrix Representation of Z Values",
    height=500,
    width=800
)

# Update x and y axes labels
fig.update_xaxes(title_text="X", row=1, col=1)
fig.update_yaxes(title_text="Y", row=1, col=1)
fig.update_xaxes(title_text="X", row=1, col=2)
fig.update_yaxes(title_text="Y", row=1, col=2)

fig.write_image("/Users/dawid.olejniczak/Documents/GitHub/playground/benchmark/ppbench_results/task_1/plotly/output.png")