import pandas as pd
df = pd.read_csv("benchmark/ppbench_results/task_0/plotly/data.csv")

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

df = pd.read_csv("benchmark/ppbench_results/task_0/plotly/data.csv")

# Reshape data into 2D arrays (assuming square root dimensions)
n = int(np.sqrt(len(df)))
if n * n != len(df):
    # If not perfect square, pad with zeros or adjust dimensions
    n = int(np.ceil(np.sqrt(len(df))))
    padded_length = n * n
    array1_padded = np.pad(df['array1'].values, (0, padded_length - len(df)), mode='constant')
    array2_padded = np.pad(df['array2'].values, (0, padded_length - len(df)), mode='constant')
else:
    array1_padded = df['array1'].values
    array2_padded = df['array2'].values

array1_2d = array1_padded.reshape(n, n)
array2_2d = array2_padded.reshape(n, n)

# Create subplots with equal height
fig = make_subplots(
    rows=1, cols=2,
    subplot_titles=('Array1 2D Image', 'Array2 2D Image'),
    horizontal_spacing=0.1
)

# Add heatmaps
fig.add_trace(
    go.Heatmap(
        z=array1_2d,
        colorscale='viridis',
        showscale=True,
        colorbar=dict(x=0.45, len=0.8)
    ),
    row=1, col=1
)

fig.add_trace(
    go.Heatmap(
        z=array2_2d,
        colorscale='plasma',
        showscale=True,
        colorbar=dict(x=1.02, len=0.8)
    ),
    row=1, col=2
)

# Update layout for equal heights and aspect ratios
fig.update_layout(
    title="2D Image Representation of DataFrame Columns",
    height=500,
    width=1000,
    annotations=[
        dict(
            text="Layout adjusted for equal heights<br>with preserved aspect ratios",
            xref="paper", yref="paper",
            x=0.5, y=1.15,
            showarrow=False,
            font=dict(size=12),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="black",
            borderwidth=1
        ),
        dict(
            text="Array1: Reshaped data<br>with viridis colormap",
            xref="paper", yref="paper",
            x=0.25, y=-0.15,
            showarrow=False,
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="gray",
            borderwidth=1
        ),
        dict(
            text="Array2: Reshaped data<br>with plasma colormap",
            xref="paper", yref="paper",
            x=0.75, y=-0.15,
            showarrow=False,
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="gray",
            borderwidth=1
        )
    ]
)

# Update axes to maintain aspect ratio
fig.update_xaxes(scaleanchor="y", scaleratio=1)
fig.update_yaxes(scaleanchor="x", scaleratio=1)

fig.write_image("/Users/dawid.olejniczak/Documents/GitHub/playground/benchmark/ppbench_results/task_0/plotly/output.png")