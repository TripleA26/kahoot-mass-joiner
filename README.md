# Kahoot Bot Mass Joiner

A powerful Python tool for mass joining Kahoot games with proxy support and automatic challenge solving.

## Features

- 🚀 **Mass Joining**: Join Kahoot games with multiple bots simultaneously
- 🔄 **Proxy Support**: Rotate through proxies from a file to avoid rate limiting
- 🧩 **Auto Challenge Solving**: Automatically solves Kahoot's WebSocket challenge
- 🎯 **Custom Usernames**: Generate unique usernames with random numbers
- ⚡ **Async Performance**: Built with asyncio for high-performance concurrent connections

## Installation

1. Clone the repository:
```bash
git clone https://github.com/TripleA26/kahoot-mass-joiner.git
cd kahoot-mass-joiner
```

## Installation

**Install required dependencies:**

```bash
pip install aiohttp
```
## Usage

### Basic Usage
```bash
python main.py
```
When prompted, enter:

Kahoot game PIN  
Number of bots to join  

## Using Proxies

Create a `proxies.txt` file in the same directory.  

Add your proxies (one per line)

Run the script and enter the game PIN and bot count when asked.

## Customizing Usernames

Change the prefix for bot names by editing the `PREFIX` variable in `main.py`:
```python
PREFIX = "Triple"
```

## Credits

Base structure inspired by [aogiribling](https://github.com/aogiribling)
