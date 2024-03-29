# -*- coding: utf-8 -*-

import datetime
import os
import random
from camel_parser.src.conll_output import print_to_conll, text_tuples_to_string
from camel_parser.src.data_preparation import get_file_type_params, parse_text
import flask
import requests
from flask import request
from pandas import read_csv
from camel_tools.utils.charmap import CharMapper

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery

from flask_cors import CORS, cross_origin
import sys
sys.path.insert(0,'camel_parser/src')

project_dir = os.path.expanduser('~/palmyra_server/palmyra_server')

# camel_tools import used to clean text
arclean = CharMapper.builtin_mapper("arclean")

#
### Get clitic features
#
clitic_feats_df = read_csv(f'{project_dir}/camel_parser/data/clitic_feats.csv')
clitic_feats_df = clitic_feats_df.astype(str).astype(object) # so ints read are treated as string objects



# This variable specifies the name of a file that contains the OAuth 2.0
# information for this application, including its client_id and client_secret.
CLIENT_SECRETS_FILE = f"{os.path.expanduser(project_dir)}/client_secret.json"

# This OAuth 2.0 access scope allows for full read/write access to the
# authenticated user's account and requires requests to use an SSL connection.
# os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly', 'https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/drive.file']
API_SERVICE_NAME = 'drive'
API_VERSION = 'v2'

app = flask.Flask(__name__)
# Note: A secret key is included in the sample so that it works.
# If you use this code in your application, replace this with a truly secret
# key. See https://flask.palletsprojects.com/quickstart/#sessions.
app.secret_key = os.getenv('FLASK_SECRET')

# app.config['CORS_HEADERS'] = 'Content-Type'

# cors = CORS(app, resources={r"/test": {"origins": 'https://voluble-fudge-4fc88e.netlify.app/'}})
cors = CORS(app, supports_credentials=True)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/')
def index():
  return print_index_table()


# @cross_origin(origin='https://voluble-fudge-4fc88e.netlify.app/',headers=['Content-Type','Authorization'])
# @cross_origin(supports_credentials=True, origins='https://voluble-fudge-4fc88e.netlify.app')
@app.route('/test')
def test_api_request():
  if 'credentials' not in flask.session:
    return flask.redirect('authorize')

  # Load credentials from the session.
  credentials = google.oauth2.credentials.Credentials(
      **flask.session['credentials'])

  drive = googleapiclient.discovery.build(
      API_SERVICE_NAME, API_VERSION, credentials=credentials)

#   files = drive.files().list().execute()

  # Save credentials back to session in case access token was refreshed.
  # ACTION ITEM: In a production app, you likely want to save these
  #              credentials in a persistent database instead.
  flask.session['credentials'] = credentials_to_dict(credentials)

#   return credentials_to_dict(credentials)
#   response = flask.jsonify(credentials_to_dict(credentials))
#   response.headers.add('Access-Control-Allow-Origin', 'https://voluble-fudge-4fc88e.netlify.app')
  cred_dict = credentials_to_dict(credentials)
  return flask.redirect(f"https://camel-lab.github.io/palmyra/viewtree.html?token={cred_dict['token']}&ak={os.getenv('API_KEY')}");
#   return flask.redirect(f"https://voluble-fudge-4fc88e.netlify.app/viewtree.html?token={cred_dict['token']}");
#   return flask.jsonify(**files)



# @cross_origin(supports_credentials=True, origins='https://voluble-fudge-4fc88e.netlify.app')
@app.route('/authorize')
def authorize():
  # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
  flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
      CLIENT_SECRETS_FILE, scopes=SCOPES)

  # The URI created here must exactly match one of the authorized redirect URIs
  # for the OAuth 2.0 client, which you configured in the API Console. If this
  # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
  # error.
  flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

  authorization_url, state = flow.authorization_url(
      # Enable offline access so that you can refresh an access token without
      # re-prompting the user for permission. Recommended for web server apps.
      access_type='offline',
      # Enable incremental authorization. Recommended as a best practice.
      include_granted_scopes='true')

  # Store the state so the callback can verify the auth server response.
  flask.session['state'] = state

  return flask.redirect(authorization_url)


@app.route('/oauth2callback')
def oauth2callback():
  # Specify the state when creating the flow in the callback so that it can
  # verified in the authorization server response.
  state = flask.session['state']

  flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
      CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
  flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

  # Use the authorization server's response to fetch the OAuth 2.0 tokens.
  authorization_response = flask.request.url
  flow.fetch_token(authorization_response=authorization_response)

  # Store credentials in the session.
  # ACTION ITEM: In a production app, you likely want to save these
  #              credentials in a persistent database instead.
  credentials = flow.credentials
  flask.session['credentials'] = credentials_to_dict(credentials)

  return flask.redirect(flask.url_for('test_api_request'))


@app.route('/revoke')
def revoke():
  if 'credentials' not in flask.session:
    return ('You need to <a href="/authorize">authorize</a> before ' +
            'testing the code to revoke credentials.')

  credentials = google.oauth2.credentials.Credentials(
    **flask.session['credentials'])

  revoke = requests.post('https://oauth2.googleapis.com/revoke',
      params={'token': credentials.token},
      headers = {'content-type': 'application/x-www-form-urlencoded'})

  status_code = getattr(revoke, 'status_code')
  if status_code == 200:
    return('Credentials successfully revoked.' + print_index_table())
  else:
    return('An error occurred.' + print_index_table())


@app.route('/clear')
def clear_credentials():
  if 'credentials' in flask.session:
    del flask.session['credentials']
  return ('Credentials have been cleared.<br><br>' +
          print_index_table())

@app.route('/parse_data', methods=['POST'])
def parse_data():
  lines = request.get_json()['sentences']
  file_type = 'text'
  
  file_type_params = get_file_type_params(lines, file_type, '', f'{project_dir}/camel_parser/models/CAMeLBERT-CATiB-biaffine.model',
      arclean, 'bert', clitic_feats_df, 'catib6', 'calima-msa-s31')
  parsed_text_tuples = parse_text(file_type, file_type_params)

  string_lines = text_tuples_to_string(parsed_text_tuples, sentences=lines)
  parsed_data = '\n'.join(string_lines)

  new_id = str(int(random.random()*100000)) + datetime.datetime.now().strftime('%s')
  
  with open(f'{project_dir}/data/temp_parsed/{new_id}', 'w') as f:
    f.write(parsed_data)

  return new_id


@app.route('/get_parsed_data', methods=['GET'])
def get_parsed_data():
  data_id = request.args.get("data_id")
  conll_file_path = f'{project_dir}/data/temp_parsed/{data_id}'
  
  data = []
  with open(conll_file_path, 'r') as f:
    data = f.readlines()
  os.remove(conll_file_path)
  
  return ''.join(data)

@app.route('/get_gapi_credentials', methods=['GET'])
def get_gapi_credentials():
  return {
    'apiKey': os.getenv('GCP_API_KEY'),
    'discovertDocs': [os.getenv('GCP_DISCOVERY_DOC')]
  }

@app.route('/get_gis_credentials', methods=['GET'])
def get_gis_credentials():
  return {
    'client_id': os.getenv('GCP_CLIENT_ID'),
    'scope': SCOPES
  }

def credentials_to_dict(credentials):
  return {'token': credentials.token,
          'refresh_token': credentials.refresh_token,
          'token_uri': credentials.token_uri,
          'client_id': credentials.client_id,
          'client_secret': credentials.client_secret,
          'scopes': credentials.scopes}

def print_index_table():
  return ('<table>' +
          '<tr><td><a href="/test">Test an API request</a></td>' +
          '<td>Submit an API request and see a formatted JSON response. ' +
          '    Go through the authorization flow if there are no stored ' +
          '    credentials for the user.</td></tr>' +
          '<tr><td><a href="/authorize">Test the auth flow directly</a></td>' +
          '<td>Go directly to the authorization flow. If there are stored ' +
          '    credentials, you still might not be prompted to reauthorize ' +
          '    the application.</td></tr>' +
          '<tr><td><a href="/revoke">Revoke current credentials</a></td>' +
          '<td>Revoke the access token associated with the current user ' +
          '    session. After revoking credentials, if you go to the test ' +
          '    page, you should see an <code>invalid_grant</code> error.' +
          '</td></tr>' +
          '<tr><td><a href="/clear">Clear Flask session credentials</a></td>' +
          '<td>Clear the access token currently stored in the user session. ' +
          '    After clearing the token, if you <a href="/test">test the ' +
          '    API request</a> again, you should go back to the auth flow.' +
          '</td></tr></table>')


if __name__ == '__main__':
  # When running locally, disable OAuthlib's HTTPs verification.
  # ACTION ITEM for developers:
  #     When running in production *do not* leave this option enabled.
  os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

  # Specify a hostname and port that are set as a valid redirect URI
  # for your API project in the Google API Console.
  app.run('localhost', 8080, debug=True)