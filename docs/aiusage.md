# Transparent Declaration of Artificial Intelligence (AI) Usage

In accordance with the NASA Space Apps Challenge rules and our commitment to Open Science, we provide the following transparent declaration regarding the use of Artificial Intelligence in our project.

## 1. Utilization of AI During the Hackathon
- **Technical Problem Solving:** AI was used as a supportive tool to overcome specific technical challenges, most notably in integrating the "Point-in-Polygon" (Ray-Casting) algorithm into the `awk` scripting language.
- **Data Processing:** AI provided informational support for the accurate parsing, processing, and validation of satellite data.
- **Data Structuring for Frontend:** AI provided structural suggestions (e.g., JSON schema formatting) to ensure seamless data consumption by the web application.

## 2. What AI Strictly Did NOT Do
- **No Data Fabrication:** AI was **never** used to generate, synthesize, or manipulate the raw data itself. All data was fetched directly from official NASA FIRMS APIs as authentic satellite telemetry.
- **Human-in-the-Loop:** AI did not execute any task autonomously. Human oversight and approval remained the absolute priority (Priority 1) at every stage.
- **Assistant, Not Creator:** Large Language Models (LLMs) were used strictly as assistant tools, not as primary creators of the project's architecture or logic.
- **Purpose-Bound Usage:** AI was consulted only when necessary for troubleshooting, optimization, or documentation.

## 3. Result and Responsibility
- **Software Assistant Role:** In this project, AI served as a *"software assistant,"* not a *"creator."* 
- **Verification:** All AI-generated code snippets, analyses, and structural suggestions were meticulously tested, verified, and integrated by human team members.
- **Accountability:** The scientific validity, data integrity, and operational accuracy of the project are **100% the responsibility of the AeroFire team**.

## 4. AI Models and Tools Used
- **DeepSeek** (Code optimization and logic assistance)
- **VS Code Copilot (GPT-Astra)** (Syntax support and boilerplate generation)
- **Claude Opus** (Documentation, architectural advice, and debugging)

## 5. Technologies and Data Sources
- **Data Sources:** NASA FIRMS (MODIS and VIIRS Satellite Data).
- **Boundary Data:** GADM (Global Administrative Areas) Province and Country border polygons.
- **Backend:** 
  - `Bash` (Core data orchestration).
  - `Awk` (Data parsing, filtering, and spatial algorithms).
  - `gnuplot` (Data visualization).
  - `Python` (Optional compatibility script for Windows environments).
  - `JSON` (Data interchange format for the frontend).
- **Frontend:** HTML, CSS, JavaScript (Leaflet Map integration).

---

**Written By:** Akay Kaya - Translated to English by Deepseek.
*Note: Some terms, code structures, and resources used in this project are subject to 3rd-party licenses.*
**Approved by:** NASA Space Apps AeroFire Team. Open for public use.
