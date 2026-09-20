#  EV Charger Finder

An agentic AI-powered EV charging station finder that helps users find suitable charging stations based on natural-language requests.

The system combines a Large Language Model, real-world EV charging station data, multiple specialized agents, and a Gradio web interface to provide charger recommendations.

---

##  Project Overview

EV Charger Finder allows users to enter requests such as:

> "I need a charger within 75 km"

or:

> "Find the nearest available charger"

The system understands the user's request, searches for nearby charging stations, checks simulated availability, calculates route information, ranks suitable stations, and performs a simulated booking.

### Example Request

```text
I need a charger within 75 km
```

The Intent Agent extracts:

```text
Intent: find_charger
Priority: nearest
Search Radius: 75 km
```

The system then searches for stations within the requested radius and presents ranked candidates.

---

## 🤖 Agentic AI Architecture

The project follows a multi-agent architecture:

```text
                    ┌─────────────────┐
                    │      User       │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   Intent Agent  │
                    │   (Groq LLM)    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Orchestrator   │
                    └────────┬────────┘
                             │
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
      Search Agent    Availability Agent   Route Agent
             │               │               │
             └───────────────┼───────────────┘
                             ▼
                    ┌─────────────────┐
                    │ Decision Agent  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Booking Agent  │
                    │   (Simulated)   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Notification    │
                    │ Agent (Simulated)│
                    └─────────────────┘
```

---

## 🧩 Agents

### 1. Intent Agent

Uses Groq's LLM to understand natural-language requests.

It extracts:

- User intent
- Charging priority
- Connector type
- Minimum charging power
- Search radius

Example:

```text
"I need a charger within 75 km"
```

is converted into structured information containing:

```text
intent = find_charger
search_radius_km = 75
```

---

### 2. Orchestrator

Coordinates the complete agent workflow.

It:

- Receives the user's request
- Calls the Intent Agent
- Determines the search radius
- Sends the request to the Search Agent
- Coordinates availability, routing, decision-making, and booking
- Handles retries when required

---

### 3. Search Agent

Retrieves real EV charging station information using the **Open Charge Map API**.

The search can be performed based on:

- Latitude
- Longitude
- Search radius

---

### 4. Availability Agent

Determines the simulated charging availability of candidate stations.

> **Note:** Availability is simulated for this project and does not represent real-time charger availability.

---

### 5. Route Agent

Calculates approximate:

- Distance
- ETA
- Reachability based on the vehicle's remaining range

---

### 6. Decision Agent

Ranks charging stations using factors such as:

- Distance
- ETA
- Charging power
- Availability
- Price information
- Reachability

The system then presents ranked candidates to the user.

---

### 7. Booking Agent

Performs a **simulated booking** for demonstration purposes.

No real charging station reservation is made.

The system can generate a simulated booking reference.

---

### 8. Notification Agent

Provides simulated booking and notification information as part of the agent workflow.

---

## 🗺️ Data Source

### Open Charge Map

The project uses **Open Charge Map** for EV charging station information.

Station information can include:

- Station name
- Location
- Distance
- Charging power
- Pricing information when available
- Other available station metadata

Availability and booking are simulated separately.

---

## 🧠 Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application |
| Gradio | Web interface |
| Groq | Live LLM inference |
| GPT-OSS-20B | Intent understanding |
| Open Charge Map | EV station data |
| Requests | API communication |
| HTML/CSS | UI customization |
| Git/GitHub | Version control |

---

## 🎨 User Interface

The application uses a light pastel **ChargeMate** interface featuring:

- Navigation bar
- AI Assistant sidebar
- EV charging assistant hero section
- Agent pipeline visualization
- Chatbot interface
- Trip & Search Settings
- Live Map Preview
- Sustainability section
- Demo Status panel
- Ranked charging station results

---

## ⚙️ Project Structure

```text
EV-Charger-Agent/
│
├── app.py
├── test_app_import.py
├── test_ui_structure.py
├── README.md
├── .gitignore
└── venv/                  # Local only, not uploaded to GitHub
```

---

## 🔑 API Configuration

The project requires API keys for external services.

### Groq API Key

Set the Groq API key as an environment variable:

```bash
export GROQ_API_KEY="YOUR_GROQ_API_KEY"
```

### Open Charge Map API Key

```bash
export OCM_API_KEY="YOUR_OCM_API_KEY"
```

**Never commit API keys directly into the source code or GitHub repository.**

---

## 💻 Installation

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd EV-Charger-Agent
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

### 3. Activate the virtual environment

#### macOS / Linux

```bash
source venv/bin/activate
```

#### Windows

```bash
venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install gradio requests
```

---

## ▶️ Running the Application

Set the required environment variables:

```bash
export GROQ_API_KEY="YOUR_GROQ_API_KEY"
export OCM_API_KEY="YOUR_OCM_API_KEY"
```

Then run:

```bash
python app.py
```

Gradio will provide a local URL similar to:

```text
http://127.0.0.1:7860
```

Open the URL in your browser.

---

## 🧪 Example Queries

Try requests such as:

```text
Find me the nearest available charger
```

```text
I need a charger within 75 km
```

```text
What's the cheapest charger nearby?
```

```text
I need the fastest charger
```

```text
Find an available charger
```

The Intent Agent interprets the request and the Orchestrator routes it through the agent pipeline.

---

## 🔋 Remaining Range

The **Remaining Range (km)** setting represents the approximate distance the vehicle can still travel before requiring a charge.

The system uses this information when determining whether a charging station is reachable.

For example:

```text
Remaining Range = 40 km
```

means the vehicle is assumed to have approximately 40 km of usable driving range remaining.

---

## 📍 Search Radius

The user can specify a search radius directly in natural language.

For example:

```text
I need a charger within 75 km
```

The Intent Agent extracts:

```text
search_radius_km = 75
```

The Orchestrator then uses the requested radius for the station search.

A manual search-radius override is also available through the UI.

---

## 🧪 Testing

The project includes basic tests for application import and UI structure.

Run:

```bash
python test_app_import.py
```

and:

```bash
python test_ui_structure.py
```

The application can also be tested manually through the Gradio interface.

---

## ⚠️ Project Limitations

This project is a prototype intended for demonstration and academic purposes.

### Availability

Charging station availability is simulated and should not be treated as live charger availability.

### Booking

Bookings are simulated. The application does not make real charging station reservations.

### Notifications

Notifications are simulated as part of the agent workflow.

### Route Information

Distance and ETA are calculated/approximated for the prototype and may not represent live navigation data.

### Pricing

Price information depends on the information available from the station data source. Some stations may not provide usable pricing information.

---

## 🔐 Security

API keys should always be stored as environment variables.

Do not commit:

```text
.env
.env.*
API keys
venv/
__pycache__/
```

The repository includes a `.gitignore` file to prevent sensitive and unnecessary files from being uploaded.

---

## 🌱 Future Enhancements

Possible future improvements include:

- Real-time charger availability
- Real-time navigation and traffic information
- Real charger reservation APIs
- EV-specific route planning
- User authentication
- Charging-session history
- Personalized charger recommendations
- Real-time notifications
- Integration with additional charging networks
- Mobile application support

---

## 🎓 Project Purpose

This project demonstrates how **Agentic AI and automation** can be applied to an EV charging use case.

Instead of relying on a single chatbot response, the system divides the task into specialized agents that collaborate to:

1. Understand the user's request
2. Search real-world station data
3. Check availability
4. Evaluate reachability
5. Rank charging stations
6. Simulate booking
7. Provide notification information

---

## 👩‍💻 Author

**Ojaswini Thote**

Computer Science & Engineering

---

## 📄 License

This project is intended for academic and educational purposes.
