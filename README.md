# Finance Tracker

A Streamlit application for extracting and tracking financial transactions from bank email notifications.

## Features

- Extract transaction details from bank notification emails using regex pattern matching
- Track and visualize your spending habits over time
- Filter transactions by date range, type, and more
- Secure authentication with Google OAuth

## Setting up HuggingFace Space Integration

This repository includes a GitHub Actions workflow that automatically creates and updates a HuggingFace Space with the same name as your repository. The Space will be a Streamlit app that mirrors this repository.

### Prerequisites

To use the HuggingFace sync feature, you'll need:

1. A HuggingFace account
2. A HuggingFace API token with write access

### Setup Instructions

1. **Get a HuggingFace API Token**:
   - Go to [HuggingFace Settings → Access Tokens](https://huggingface.co/settings/tokens)
   - Create a new token with `write` permissions
   - Copy the token value

2. **Add Repository Secrets in GitHub**:
   - Go to your GitHub repository → Settings → Secrets and Variables → Actions
   - Add the following secrets:
     - `HF_TOKEN`: Your HuggingFace API token
     - `HF_USERNAME`: Your HuggingFace username
     - Optional: `EMAIL_SECRET` and `GOOGLE_CLIENT_SECRET` if your app needs them

3. **Trigger the Workflow**:
   - The workflow will run automatically on every push to the main/master branch
   - You can also manually trigger it from the Actions tab in GitHub

### How It Works

The workflow uses the official [Hugging Face Spaces GitHub Action](https://github.com/huggingface/huggingface-spaces) to:

1. Check if your Hugging Face token works
2. Create a Hugging Face Space with the same name as your GitHub repository
3. Configure the Space with Streamlit as the SDK
4. Deploy your code to the Space
5. Set up any required secrets

### Troubleshooting

If you encounter issues:

1. **Authentication Errors**: Make sure your HF_TOKEN has write permissions and hasn't expired
2. **Permission Issues**: Verify your Hugging Face account has permission to create Spaces
3. **Name Conflicts**: Ensure no other Space with the same name already exists
4. **Missing Variables**: Check that all required secrets are set in GitHub

## Local Development

To run this application locally:

```bash
# Clone the repository
git clone https://github.com/yourusername/Finance-Tracker.git
cd Finance-Tracker

# Install dependencies
pip install -r requirements.txt

# Run the Streamlit app
streamlit run app.py
```

## Configuration

The application requires Google OAuth credentials to access Gmail:

1. Create a Google Cloud project
2. Enable the Gmail API
3. Create OAuth credentials
4. Download the credentials as `credentials.json` and place it in the project root

## License

This project is licensed under the MIT License - see the LICENSE file for details. 

