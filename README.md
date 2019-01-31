# Slackxporter
Export messages from slack to textfiles.

## Prerequisites
- Python 2.7
- [Python slack client](https://github.com/slackapi/python-slackclient) - install via pip: `pip install slackclient`
- Get a legacy [slack token](https://api.slack.com/custom-integrations/legacy-tokens)

## Usage
- Specify your slack token `slack_token`
- Set conversations you want to export in call to `get_conversations()` - to export all, specify `all_conversations`
- Specify channel to export as first argument to the program
