import dash
from dash import html, dcc

dash.register_page(__name__, path='/')

layout = html.Div([
    html.Br(),
    html.H2('ReadMe'),
    html.Div('Ephys Dashboard User Wiki'),
    dcc.Markdown('''
                 Under construction ...
                 
                 
                 
                 
                 '''),
    html.Br(),
    html.Br(),
    html.Br(),
    html.Hr(),
    html.Div([html.P("Braingeneers@UCSC"),
              html.P("All Rights Reserved")])
])