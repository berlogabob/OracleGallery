> Text-only extraction of the EchoDraw explanatory note (Andrey Dyakov, 2026-01-08). Original with embedded images: author's archive. Work photos: https://github.com/berlogabob/echodraw-project

# **Project Explanatory Note**

**«EchoDraw: Interactive Generative Plotter with Real-Time Video Processing and Machine Learning Elements»**

**Author:** Andrey Dyakov  
**Date:** January 8, 2026

### **1\. Introduction and Scientific Significance of the Project**

This project involves the development of an interactive physical computing system based on converting the **NEJE Master 2S Plus** laser engraver (working area 255 × 420 mm, N40630 laser module) into a multifunctional XY-plotter using pens as the tool. The system enables real-time user interaction with the machine via a web camera: image capture, detection of gestures, poses, faces, and sounds → generation and modification of abstract patterns → transmission of control commands in G-code format → physical drawing with surface adaptation and support for continuous material feed.

The project is structured around three interconnected modules (ideas), each with relative autonomy, allowing for phased development and testing. This modular approach facilitates systematic functionality buildup, risk minimization, and the ability to demonstrate intermediate results. The development focuses on accessible technologies (ESP32-compatible controllers, browser-based libraries p5.js and ml5.js, cross-platform development with Flutter), making the project reproducible and suitable for educational or laboratory purposes.

### **2\. Description of the Three Main Project Modules and Their Development Stages**

**Module 1: Hardware Component of the Plotter Based on NEJE**  
This module creates the physical execution system — converting the engraver into a plotter with extended capabilities. It uses **FluidNC** firmware (an evolution of GRBL for ESP32), providing WiFi connectivity, quiet operation of TMC2209 drivers, and flexible configuration via YAML files. The development can be separated into an independent educational course for enthusiasts.

**Development stages (in increasing complexity):**

1. Analysis of the NEJE kinematic scheme and integration of the FluidNC TMC2209 controller.  
2. Firmware flashing and configuration of the basic file (steps/mm, speeds).  
3. Development of a single-pen printing head (servo mechanism for lifting/lowering, G-code testing).  
4. Integration of a load sensor (FSR or load cell with HX711) for adaptation to curved surfaces.  
5. Creation of a two-color printing module based on a "rocker" mechanism (one servo, three positions: neutral — lift, ±45° — lowering one of the colors).  
6. Combined module (two-color \+ load sensor). 7–10. Material feed system:  
   * Variant A: Closed conveyor belt (infinite feed, overwrite capability; tension mechanism, 1–2 stepper/servo motors; step or continuous scroll modes).  
   * Variant B: Roll feed (rolling mechanism; step/continuous speed modes; optional semi-automatic cutting or shredder integration).

**Module 2: Generative Core Based on p5.js and ml5.js**  
This module handles video stream processing and pattern generation, bridging digital reality digitization to plotter control commands. Testing uses various pen types (ballpoint and capillary).

**Development stages:**

1. Implementation of a generator for simple geometric patterns with a single continuous line.  
2. Creation of a layer overlay system (combination matrix with adjustable number).  
3. Development of a basic interface with ready G-code sending function.  
4. Improvement of layer overlay (introduction of masks based on Perlin noise and other textures).  
5. Transition to real-time mode (continuous G-code streaming in a loop).  
6. Integration of web camera and filter library (edge detection, pixelization, simplification, color transformations).  
7. Implementation of machine learning elements (ml5.js: hand detection — handpose, pose — posenet, face — face-api, sound; influence on generation and filter parameters).

**Module 3: Cross-Platform Wrapper on Flutter**  
This module provides a unified user interface for all system components (web and mobile versions).

**Development stages:**

1. Basic application with plotter connection and G-code file sending.  
2. Integration of pattern generators and on-demand G-code generation.  
3. Implementation of layer and blending system.  
4. Addition of camera processing and filters.  
5. Full integration (real-time mode, ML, conveyor control).

### **3\. Module Interconnections and Integration into a Unified System**

The modules have pronounced interdependence, forming a hierarchical structure:

* **Module 1** acts as the execution mechanism, receiving G-code via WiFi/WebSocket (native FluidNC support).  
* **Module 2** generates content and provides intelligent interaction, forming commands for Module 1\.  
* **Module 3** serves as the interface layer, integrating Module 2 (embedding p5.js-canvas) and providing convenient access to Module 1\.

Integration occurs phased: first file transfer → real-time streaming → full synchronization (camera → ML → pattern → plotter). The resulting system is an interactive installation where digital reality transformation immediately materializes in a physical drawing.

### **4\. Methodology and Approaches to Problem Solving**

Development follows an incremental principle: each stage ends with a working prototype. Hardware modifications use 3D printing and standard components. The software part relies on open libraries (p5.js, ml5.js, FluidNC). Testing includes calibration (steps/mm, servo angles), pen type comparison, and material feed mode validation.

### **5\. Approximate Work Schedule**

(Calculation for 6–8 months at 6 hours per week load):

* Months 1–2: Stages 1–3 of Module 1 \+ basic stages of Module 2\.  
* Months 2–4: Full Module 2 (including ML) \+ upgrades of Module 1\.  
* Months 4–7: Conveyor system of Module 1\.  
* Months 7–8: Full Module 3 \+ final integration and testing.

### **6\. Budget Estimate**

(Overall limit — 500 €):

* Basic hardware: 120–150 €.  
* Upgrades (FSR, two-color module): 80 €.  
* Conveyor system: 150–200 €.  
* Reserve (materials, delivery): 50 €.  
  **Total:** 400–480 €.

### **7\. Conclusion**

The **EchoDraw** project demonstrates a systematic approach to creating an interactive system at the intersection of physical computing, generative art, and machine learning. The modular structure with clearly defined stages ensures controlled development and intermediate demonstrations. Project implementation will contribute to laboratory practice and can serve as a basis for educational initiatives.

Ready for discussion and revisions.  
**Contact:** Andrey Dyakov  
**Email:** andre.berloga@gmail.com

### **8\. Examples of Pen-Plotter Works**












See work examples and photos in the original repo: https://github.com/berlogabob/echodraw-project
