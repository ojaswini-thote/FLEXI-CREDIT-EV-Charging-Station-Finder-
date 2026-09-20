#  EV Charger Finder

An **Agentic AI-powered EV Charging Station Finder** that helps users find suitable electric vehicle charging stations using natural-language requests.

The system uses a **multi-agent architecture** where specialized agents work together to understand the user's request, search real charging-station data, check simulated availability, estimate route information, rank suitable chargers, and simulate a booking.

---

##  Project Overview

EV Charger Finder allows users to enter requests such as:

- "Find the nearest EV charger"
- "I need a charger within 75 km"
- "Find an available charger near me"
- "Find a charger with high power"
- "What's the cheapest charger nearby?"

The system interprets the request using an LLM-powered Intent Agent and then coordinates multiple specialized agents to produce a charging-station recommendation.

The application provides an interactive web interface built using **Gradio**.

---

## 🤖 Agentic AI Architecture

The project follows a multi-agent workflow:

```text
                         User
                           │
                           ▼
                    ┌──────────────┐
                    │ Intent Agent │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Orchestrator │
                    └──────┬───────┘
                           │
          ┌────────────────┼─────────────────┐
          ▼                ▼                 ▼
   Search Agent     Availability Agent   Route Agent
          │                │                 │
          └────────────────┼─────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Decision Agent│
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Booking Agent│
                    └──────┬───────┘
                           │
                           ▼
                  Notification Agent
                           │
                           ▼
                       Response
```

---

##  Agents

### 1. Intent Agent

The Intent Agent understands the user's natural-language request.

It extracts information such as:

- User intent
- Search radius
- Priority
- Connector type, when specified
- Minimum charging power, when specified

The project uses:

**Groq API + GPT-OSS-20B**

for live intent extraction.

Example:

```text
User:
I need a charger within 75 km

Intent Agent:
intent = find_charger
search_radius_km = 75
priority = nearest
```

---

### 2. Orchestrator

The Orchestrator coordinates the complete agent workflow.

It:

1. Receives the interpreted request.
2. Determines the search parameters.
3. Calls the required agents.
4. Collects their results.
5. Passes the results to the Decision Agent.
6. Coordinates booking and notification simulation.
7. Returns the final response to the user.

---

### 3. Search Agent

The Search Agent retrieves EV charging-station information using:

**Open Charge Map API**

The project uses real-world charging-station data rather than a completely synthetic station database.

Information can include:

- Station name
- Location
- Distance
- Charging power
- Charging station information
- Other available station metadata

---

### 4. Availability Agent

The Availability Agent determines the simulated charging availability of stations.

Availability is **simulated for this academic project**.

Possible states include:

- Available
- Limited
- Occupied

This allows the agent workflow to demonstrate real-time-style decision making without requiring access to private charger operator systems.

---

### 5. Route Agent

The Route Agent estimates:

- Distance
- Approximate ETA
- Reachability based on remaining EV range

The route/ETA values are **approximated for the project demonstration** and should not be treated as turn-by-turn navigation.

---

### 6. Decision Agent

The Decision Agent evaluates available and reachable charging stations.

Candidates are ranked using factors such as:

- Distance
- Estimated travel time
- Charging power
- Price
- Availability
- Reachability

The system produces a ranked list of suitable charging stations.

---

### 7. Booking Agent

The Booking Agent demonstrates the booking stage of the agentic workflow.

**Booking is simulated.**

No real charging-station reservation or payment is performed.

The system generates a simulated booking confirmation and reference number for demonstration purposes.

---

### 8. Notification Agent

The Notification Agent simulates the final notification stage after a booking.

It demonstrates how a completed agent workflow could communicate the result to the user.

No real SMS, email, or external notification is sent.

---

## 🌐 Real vs Simulated Components

| Component | Implementation |
|---|---|
| Intent understanding | **Live Groq API + GPT-OSS-20B** |
| EV station data | **Open Charge Map API** |
| Station availability | Simulated |
| Route/ETA | Approximate calculation |
| Reachability | Calculated from remaining range |
| Station ranking | Implemented by Decision Agent |
| Booking | Simulated |
| Notification | Simulated |
| User Interface | Gradio |

This separation is intentional because the project is designed as an academic demonstration of an Agentic AI workflow.

---

## 🎨 User Interface

The project uses **Gradio** to provide an interactive web interface.

The interface includes:

- ChargeMate dashboard
- AI Assistant section
- Natural-language chat
- Agent pipeline visualization
- Trip & Search Settings
- Latitude input
- Longitude input
- Remaining Range input
- Search Radius override
- Live Map Preview
- Charging-station results
- Ranked candidate table
- Simulated booking results

---

## 📍 Trip & Search Settings

The interface allows the user to provide:

### Latitude

The latitude of the starting location.

Example:

```text
21.1263
```

### Longitude

The longitude of the starting location.

Example:

```text
79.1600
```

### Remaining Range

The estimated distance that the EV can still travel before requiring a charge.

Example:

```text
100 km
```

### Search Radius

The maximum distance within which the system should search for charging stations.

Example:

```text
75 km
```

The search radius can also be extracted automatically from the user's natural-language request.

For example:

```text
I need a charger within 75 km
```

results in:

```text
Search radius = 75 km
```

---

## 🔄 Example Workflow

A user enters:

```text
I need a charger within 75 km
```

The system performs the following workflow:

```text
1. User enters natural-language request
             ↓
2. Intent Agent extracts search radius
             ↓
3. Orchestrator receives search parameters
             ↓
4. Search Agent queries Open Charge Map
             ↓
5. Availability Agent simulates availability
             ↓
6. Route Agent estimates distance and ETA
             ↓
7. Reachability is checked using remaining range
             ↓
8. Decision Agent ranks candidates
             ↓
9. Booking Agent simulates booking
             ↓
10. Notification Agent simulates confirmation
             ↓
11. Final result displayed in Gradio
```

---

## 🛠️ Technologies Used

### Programming Language

- Python

### AI / LLM

- Groq API
- GPT-OSS-20B

### Data Source

- Open Charge Map API

### Web Interface

- Gradio
- HTML
- CSS

### HTTP / API Communication

- Python `requests`

### Development Tools

- Visual Studio Code
- Git
- GitHub

### Deployment

- Render

---

## 📁 Project Structure

```text
FLEXI-CREDIT-EV-Charging-Station-Finder/
│
├── EV-Charger-Agent/
│   ├── app.py
│   └── README.md
│
├── .gitignore
├── .python-version
└── requirements.txt
```

### Main Files

#### `EV-Charger-Agent/app.py`

Contains the main application including:

- Agent implementations
- Orchestrator
- API integration
- Charging-station search
- Ranking
- Simulated booking
- Gradio interface
- Custom UI styling

#### `requirements.txt`

Contains the Python packages required to run the application.

#### `.python-version`

Specifies the Python version used for deployment compatibility.

#### `.gitignore`

Prevents files such as virtual environments, Python cache files, environment files, and IDE files from being uploaded to GitHub.

---

## 🔑 API Configuration

The project requires two API keys:

### Groq API Key

Used by the Intent Agent for live natural-language intent extraction.

### Open Charge Map API Key

Used by the Search Agent to retrieve charging-station information.

API keys should **never be written directly inside the source code or committed to GitHub**.

Set them as environment variables.

### macOS / Linux

```bash
export GROQ_API_KEY="YOUR_GROQ_API_KEY"
export OCM_API_KEY="YOUR_OCM_API_KEY"
```

Then run the application.

---

## ▶️ Running Locally

### 1. Clone the repository

```bash
git clone https://github.com/ojaswini-thote/FLEXI-CREDIT-EV-Charging-Station-Finder-.git
```

### 2. Open the project

```bash
cd FLEXI-CREDIT-EV-Charging-Station-Finder
```

### 3. Create a virtual environment

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Set API keys

```bash
export GROQ_API_KEY="YOUR_GROQ_API_KEY"
export OCM_API_KEY="YOUR_OCM_API_KEY"
```

### 6. Run the application

```bash
python EV-Charger-Agent/app.py
```

The Gradio application will provide a local URL that can be opened in a browser.

---

## ☁️ Deployment

The application is deployed using **Render**.

The deployment uses:

### Build Command

```bash
pip install -r requirements.txt
```

### Start Command

```bash
python EV-Charger-Agent/app.py
```

The required API keys are configured as environment variables in the deployment platform.

---

## 🧪 Testing

Example test query:

```text
I need a charger within 75 km
```

Expected behavior:

```text
Intent:
find_charger

Search Radius:
75 km

Search:
Charging stations retrieved from Open Charge Map

Availability:
Simulated

Route:
Distance and ETA estimated

Decision:
Candidates ranked

Booking:
Simulated confirmation generated
```

---

## 📊 Example Output

A typical result contains:

```text
Search:
25 stations found

Availability:
19 available

Reachability:
4 reachable on the remaining range

Booked:
DNR Fuel Point

Distance:
59.8 km

ETA:
89.7 min

Power:
120 kW

Price:
Rs14

Status:
confirmed

Reference:
Generated simulated booking reference
```

The exact results can change because the charging-station data retrieved from Open Charge Map may vary.

---

## ⚠️ Limitations

This project is an academic prototype and has several limitations:

1. Charging availability is simulated.
2. Booking is simulated.
3. No real payment is performed.
4. No real charging-station reservation is created.
5. Route and ETA values are approximate.
6. The system does not provide turn-by-turn navigation.
7. Charger operator authentication is not implemented.
8. Notification delivery is simulated.
9. Real-time charger availability from individual charging operators is not directly accessed.

---

## 🚀 Future Enhancements

Possible future improvements include:

- Real-time charger availability
- Real booking integration
- Payment integration
- Google Maps or Mapbox route integration
- Turn-by-turn navigation
- EV connector compatibility filtering
- Real-time pricing
- User accounts and authentication
- Booking history
- Email/SMS notifications
- More sophisticated route optimization
- Charging-time prediction
- Battery consumption prediction
- Multi-stop EV trip planning

---

## 🎓 Academic Purpose

This project demonstrates the use of **Agentic AI and Automation** concepts through a practical EV charging use case.

The main focus is on demonstrating how multiple specialized agents can collaborate to transform a natural-language request into a sequence of actions:

```text
Understand → Search → Check Availability → Plan Route
       → Make Decision → Simulate Booking → Notify
```

The project combines:

- Large Language Models
- Agent orchestration
- API integration
- Real-world data
- Decision making
- Automation
- Web-based interaction

---

## 👩‍💻 Author

**Ojaswini Thote**

B.Tech Computer Science and Engineering

Symbiosis Institute of Technology, Nagpur

---

## 🎓 Project Type

**Academic Mini Project / Flexi Credit Course**

**Course:** Agentic AI & Automation

---

## 🔒 Security Note

Never commit API keys, passwords, tokens, or other secrets to GitHub.

Use environment variables for sensitive configuration.

The repository intentionally excludes:

```text
.env
.env.*
venv/
.venv/
__pycache__/
*.pyc
```

---

## 📜 License

This project is developed for academic and educational purposes.
