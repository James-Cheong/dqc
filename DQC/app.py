import dash
import dash_html_components as html

app = dash.Dash(__name__)

app.layout = html.H1('DQC Dashboard test！')

if __name__ == '__main__':
    app.run_server()