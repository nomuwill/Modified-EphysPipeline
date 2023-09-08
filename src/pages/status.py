import dash
from dash import html, dcc, callback, Input, Output, State, ctx
from dash import dash_table
import dash_bootstrap_components as dbc
import braingeneers.utils.s3wrangler as wr


# TODO: send over job csv id from job_center page


dash.register_page(__name__)

layout = dbc.Container([
    html.H2("Job Status"),
    # html.Br(),
    html.Hr(),
    ])