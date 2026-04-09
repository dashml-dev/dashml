import pandas as pd
df = pd.read_csv("benchmark/ppbench_results/task_2/plotly/data.csv")

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

df = pd.read_csv("benchmark/ppbench_results/task_2/plotly/data.csv")

fig = make_subplots(rows=1, cols=2, 
                    subplot_titles=("Fixed Sizing", "Fixed and Scaled Sizing"))

fig.add_trace(go.Scatter(x=df.index, y=df['Data'], 
                        mode='lines', 
                        line=dict(color='blue'),
                        name='Fixed Sizing'), 
              row=1, col=1)

fig.add_trace(go.Scatter(x=df.index, y=df['Data'], 
                        mode='lines', 
                        line=dict(color='blue'),
                        name='Fixed and Scaled Sizing'), 
              row=1, col=2)

fig.update_layout(
    title="Data Visualization with Different Sizing Approaches",
    showlegend=False,
    plot_bgcolor='white'
)

fig.update_xaxes(showgrid=False, showline=True, linecolor='lightgray')
fig.update_yaxes(showgrid=False, showline=True, linecolor='lightgray')

fig.update_xaxes(range=[0, len(df)-1], row=1, col=1)
fig.update_yaxes(range=[df['Data'].min()-0.5, df['Data'].max()+0.5], row=1, col=1)

fig.update_xaxes(autorange=True, row=1, col=2)
fig.update_yaxes(autorange=True, row=1, col=2)

fig.write_image("/Users/dawid.olejniczak/Documents/GitHub/playground/benchmark/ppbench_results/task_2/plotly/output.png")