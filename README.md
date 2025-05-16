# JoyAndCo Product Feed Generator

This tool automatically crawls the JoyAndCo website (https://joyandco.com), extracts all product information, and generates properly formatted product feeds for Google Merchant Center and Meta Catalog to run shopping ads.

## Features

- 🤖 Automated crawler that handles AJAX "view more" buttons
- 🔄 Daily automatic updates via GitHub Actions
- 📋 Generates both Google and Meta compatible XML/CSV feeds
- 📊 Optional Streamlit dashboard for monitoring and manual controls
- 🔍 Robust error handling and logging
- 🛒 Support for all product attributes required by shopping ads

## How It Works

1. The crawler navigates to the JoyAndCo product pages
2. It clicks the "view more" button repeatedly until all products are loaded
3. It extracts all product links and visits each product page
4. Product details are collected (title, description, price, image, etc.)
5. The data is processed and formatted into compliant feed files
6. GitHub Actions commits and pushes the updated feeds daily
7. Google and Meta shopping platforms fetch the feeds from the raw GitHub URLs

## Setup Instructions

### Prerequisites

- Python 3.8+
- GitHub account
- Google Merchant Center account and/or Meta Business Manager account

### Installation

1. Clone this repository:
