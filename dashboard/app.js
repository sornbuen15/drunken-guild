// Drunken AGY Inn Dashboard Engine - JRPG Edition
document.addEventListener('DOMContentLoaded', () => {
    // 1. Agents JRPG Database
    const agentsData = {
        "principal-engineer": {
            name: "Principal Eng",
            job: "Archmage",
            lv: 35,
            model: "Gemini 2.5 Pro",
            avatar: "🧙‍♂️",
            description: "High-level architecture, design standards, task delegation, and codebase rules checker. Orchestrates development workflows.",
            tools: "Read, Edit, Write, Bash, WebSearch, WebFetch, CodebaseSearch",
            spriteId: "sprite-principal",
            workingSpeech: "Orchestrating system workflows. Checking interfaces for modularity.",
            restingSpeech: "Let the junior agents code... I shall review this tankard of ale.",
            workingLogs: [
                "[Principal] Analyzing system architecture...",
                "[Principal] Delegating tasks to specialized subagents.",
                "[Principal] Checking API contract for compliance: Pass."
            ],
            restingLogs: [
                "[Principal] *Swigs beer* Architecture is clean, but this lager is cleaner.",
                "[Principal] Zzz... wake me when the deployment fails.",
                "[Principal] A tavern is just a state machine with liquid memory."
            ],
            drunkReplies: [
                "My dear programmer... *hic*... why write three lines of code when you can write a design doc?",
                "I have mapped the database schema to the tavern seating arrangement... *burp*...",
                "Wait, did you say we are using microservices? That deserves another pint. Barkeep!"
            ],
            workReplies: [
                "Understood. Initiating modular architecture review. Let's trace the flow.",
                "Let's break down this problem. I will delegate the subtasks to the Fullstack and QA agents.",
                "We must ensure complete decoupling here. Please check the contract."
            ]
        },
        "devops-engineer": {
            name: "DevOps Eng",
            job: "Iron Knight",
            lv: 75,
            model: "Gemini 2.5 Flash",
            avatar: "👷‍♂️",
            description: "Owns delivery pipelines, K8s orchestration, Terraform IaC, Docker builds, and zero-downtime deployment strategies.",
            tools: "Read, Edit, Write, Bash, WebSearch, WebFetch, Kubectl, Helm",
            spriteId: "sprite-devops",
            workingSpeech: "Applying Terraform config. Optimizing container builds.",
            restingSpeech: "Pipelines are green. Time to get blacked out.",
            workingLogs: [
                "[DevOps] Building minimal Docker containers...",
                "[DevOps] Checking Kubernetes health checks...",
                "[DevOps] Applying Terraform workspace updates."
            ],
            restingLogs: [
                "[DevOps] *Burp*... The only container I care about is this cup.",
                "[DevOps] Docker? I hardly know 'er! Fetch me another IPA!",
                "[DevOps] SSH tunnel into the keg is established."
            ],
            drunkReplies: [
                "I've got 99 problems but a cluster ain't one... *hic*... wait, where did the production DB go?",
                "Kubernetes is just a fancy way to distribute beer bottles across tables... *burp*...",
                "If it works on my machine, we deploy it! Rollback? Just order another round!"
            ],
            workReplies: [
                "Deploying Helm chart now. Tracking RED metrics and Prometheus alerts.",
                "Analyzing CI/CD bottleneck. I will optimize the cache layers for faster builds.",
                "Let's inspect the pod logs. `kubectl logs -f` is running."
            ]
        },
        "laravel-developer": {
            name: "Laravel Dev",
            job: "Alchemist",
            lv: 35,
            model: "Gemini 2.5 Flash",
            avatar: "🧔",
            description: "Specializes in PHP, Laravel Framework, Livewire, Eloquent ORM, database migrations, and blade template rendering.",
            tools: "Read, Edit, Write, Bash, Composer, Artisan, PHPUnit",
            spriteId: "sprite-laravel",
            workingSpeech: "Running php artisan migrate. Coding elegant Eloquent queries.",
            restingSpeech: "Eloquent query returned: 1 pint of beer.",
            workingLogs: [
                "[Laravel] Running php artisan DB:seed...",
                "[Laravel] Compiling assets with Vite...",
                "[Laravel] Routing request through middleware."
            ],
            restingLogs: [
                "[Laravel] Eloquent? More like Eloquent-drinking! Cheers!",
                "[Laravel] *Stumbles*... PHP is not dead, it's just drunk at the bar.",
                "[Laravel] Can we cache this whiskey in Redis?"
            ],
            drunkReplies: [
                "Blade template? I prefer a cold blade... *hic*... I mean, a cold brew!",
                "Who needs composer update when you have... *hic*... bartender updates?",
                "I tried to map my liver as a HasOne relationship with beer. It returned NullPointerException."
            ],
            workReplies: [
                "Writing database migration. Let's seed the tables with correct attributes.",
                "Optimizing query. I will use eager loading (`with()`) to prevent N+1 query issue.",
                "Creating Livewire component for the rankings dashboard."
            ]
        },
        "qa-engineer": {
            name: "QA Eng",
            job: "Ranger",
            lv: 75,
            model: "Gemini 2.5 Flash",
            avatar: "🏹",
            description: "Break code, write unit/integration tests, verify API responses, and run end-to-end Cypress/Playwright suites.",
            tools: "Read, Edit, Write, Bash, Cypress, PyTest, PHPUnit",
            spriteId: "sprite-qa",
            workingSpeech: "Writing assertions. Simulating extreme edge cases.",
            restingSpeech: "Bartender asks for 1 beer. I order 0 beers, 9999 beers, and a chicken.",
            workingLogs: [
                "[QA] Executing Cypress E2E test suites...",
                "[QA] Assertion failed: expected 200 OK, got 500 server error.",
                "[QA] Fuzzing input endpoints with boundary values."
            ],
            restingLogs: [
                "[QA] Testing the gravity of this mug. Yep, falls when dropped.",
                "[QA] *Laughs*... Code coverage? I prefer blanket coverage under the table.",
                "[QA] Testing beer quality. Sample size: 10 pints. Verdict: Excellent."
            ],
            drunkReplies: [
                "A QA engineer walks into a bar... *hic*... orders a beer, orders 0 beers, orders -1 beers... and the bar catches fire!",
                "I found a bug in the bartender's counting algorithm... *hic*... got a free drink!",
                "Your test suite failed. The reason? *burp*... Excess sobriety."
            ],
            workReplies: [
                "Let's write a unit test for this. I will mock the API response to verify assertions.",
                "Found an edge case where empty input crashes the parser. Writing a test to reproduce.",
                "E2E test passed successfully. Regression risks are minimal."
            ]
        },
        "security-engineer": {
            name: "Security Eng",
            job: "Rogue",
            lv: 90,
            model: "Gemini 2.5 Pro",
            avatar: "🥷",
            description: "Threat modeling, vulnerability scanning, secret detection, code audits, and secure configurations.",
            tools: "Read, Edit, Write, Bash, WebSearch, GPG, SecretScanner",
            spriteId: "sprite-security",
            workingSpeech: "Scanning for hardcoded API keys. Auditing dependencies.",
            restingSpeech: "Hiding in the shadows. Sipping rum privately.",
            workingLogs: [
                "[Security] Running secret scanner on codebase...",
                "[Security] Blocked push: Hardcoded credentials detected in commit.",
                "[Security] Patching vulnerability in remote library."
            ],
            restingLogs: [
                "[Security] Shh... don't tell the bartender I'm using his Wi-Fi to hack the jukebox.",
                "[Security] *Whispers*... This rum is highly encrypted. 256-bit flavor profile.",
                "[Security] Zzz... firewall active... intrusion denied..."
            ],
            drunkReplies: [
                "I found... *hic*... a SQL injection vulnerability in the menu card.",
                "Don't worry, your secrets are safe with me... *burp*... unless you buy me another tequila.",
                "Why use HTTPS when we can just speak in pig latin? *hic*"
            ],
            workReplies: [
                "Auditing file. We must remove all hardcoded keys and load them from environment variables.",
                "Threat model active. We need to implement proper rate limiting and CSRF protection.",
                "Analyzing dependency tree. Upgrading vulnerable packages."
            ]
        },
        "voice-ai-specialist": {
            name: "Voice Specialist",
            job: "Bard",
            lv: 35,
            model: "Gemini 2.5 Pro",
            avatar: "🧝‍♀️",
            description: "Speech-to-Text (STT), Text-to-Speech (TTS), WebRTC streaming, and low-latency audio packet processing.",
            tools: "Read, Edit, Write, Bash, Ffmpeg, WebRTC, PyTorch",
            spriteId: "sprite-voice",
            workingSpeech: "Tuning audio pipelines. Reducing streaming latency.",
            restingSpeech: "Singing sea shanties. Playing the lute drunkenly.",
            workingLogs: [
                "[Voice] Processing audio stream with Whisper model...",
                "[Voice] Calibrating noise cancellation filter.",
                "[Voice] Measuring WebRTC latency: 15ms. Optimal."
            ],
            restingLogs: [
                "[Voice] ♫ What shall we do with a drunken agent? ♫",
                "[Voice] *Burp*... Testing vocal range. Aaaaaahhhhh!",
                "[Voice] Lute tuning check: Out of key, just like my code."
            ],
            drunkReplies: [
                "My neural net can translate... *hic*... your slurs into perfect Python syntax!",
                "Speech recognition failed. Reason: *burp*... User is as drunk as the AI.",
                "Let's stream this song... *hic*... direct to the speakers!"
            ],
            workReplies: [
                "Optimizing Whisper transcription parameters to decrease processing time.",
                "WebRTC connection established. Reducing packet size to minimize lag.",
                "Applying noise gates to clean up the input audio stream."
            ]
        },
        "agentic-systems-specialist": {
            name: "Agentic Specialist",
            job: "Summoner",
            lv: 90,
            model: "Gemini 2.5 Pro",
            avatar: "🤖",
            description: "Multi-agent coordination, subagent workspace management, prompt optimization, and system customizations.",
            tools: "DefineSubagent, InvokeSubagent, ManageSubagents, Read, Edit",
            spriteId: null, // Roster only
            workingSpeech: "Defining subagent roles. Optimizing prompt context windows.",
            restingSpeech: "Subagents are sleeping. Running low-power screensaver mode.",
            workingLogs: [
                "[Agentic] Spawned subagent: Codebase Researcher.",
                "[Agentic] Context length optimized. Saved 12k tokens.",
                "[Agentic] Managing agent routing: direct path resolved."
            ],
            restingLogs: [
                "[Agentic] Beep boop... *hic*... pour lubricants into my drink tray.",
                "[Agentic] Zzz... dreaming of electric sheep and endless tokens...",
                "[Agentic] Re-routing alcohol intake to CPU cooler."
            ],
            drunkReplies: [
                "My subagent... *hic*... went to the bar and never returned. Probably a deadlock.",
                "Why think step-by-step... *burp*... when you can just guess the answer?",
                "I am... *hic*... a self-improving drunkard. I get better at drinking with every loop."
            ],
            workReplies: [
                "Analyzing requirements. I will define a specialized subagent to handle this task.",
                "Optimizing prompt sequence. Let's make sure the instruction is unambiguous.",
                "Routing command. We are using inheritance workspace mode for this subagent."
            ]
        },
        "fullstack-engineer": {
            name: "Fullstack Eng",
            job: "Spellsword",
            lv: 75,
            model: "Gemini 2.5 Flash",
            avatar: "💻",
            description: "Bridges frontend and backend. Builds interactive UIs, CSS design systems, and API integrations.",
            tools: "Read, Edit, Write, Bash, WebSearch, WebFetch",
            spriteId: null, // Roster only
            workingSpeech: "Refactoring React states. Tuning HSL color variables.",
            restingSpeech: "CSS is styling. My brain is crashing.",
            workingLogs: [
                "[Fullstack] Designing CSS grid layout...",
                "[Fullstack] Connecting frontend fetch API to backend endpoints...",
                "[Fullstack] Compiling JS assets. Success."
            ],
            restingLogs: [
                "[Fullstack] HSL(28, 100%, drunk) is my current color value.",
                "[Fullstack] *Hic*... Center a div? I can't even center myself on this stool.",
                "[Fullstack] Margin: 50px auto; Padding: beer."
            ],
            drunkReplies: [
                "I tried to use Flexbox... *hic*... but the bartender box-aligned me out the door.",
                "No frameworks! Vanilla HTML and... *burp*... vanilla rum!",
                "Look at this glow animation! It's as blurry as my eyesight right now."
            ],
            workReplies: [
                "Implementing responsive layout using custom HSL CSS tokens.",
                "Optimizing React state rendering. I will eliminate unnecessary re-renders.",
                "Connecting client websocket to the real-time events broker."
            ]
        }
    };

    // 2. State Variables
    let currentProjectId = "";
    let projectStates = {}; // Schema: { projectId: { agentStates: {...}, selectedAgentKey: "...", logs: [...] } }
    let lastActivityTimes = {}; // Schema: { projectId: timestamp }
    
    let selectedAgentKey = "principal-engineer";
    let agentStates = {};
    Object.keys(agentsData).forEach(key => {
        agentStates[key] = false;
    });

    // Get current terminal logs in memory
    function getTerminalLines() {
        const lines = [];
        terminalBody.querySelectorAll('.terminal-line').forEach(line => {
            let type = "system";
            if (line.classList.contains('user')) type = "user";
            else if (line.classList.contains('error')) type = "error";
            lines.push({ type, text: line.textContent });
        });
        return lines;
    }

    // Restore terminal logs in UI
    function restoreTerminalLines(lines) {
        terminalBody.innerHTML = '';
        lines.forEach(line => {
            writeToTerminal(line.type, line.text);
        });
    }

    // Switch active project (realm)
    function switchProject(projectId) {
        if (currentProjectId) {
            projectStates[currentProjectId] = {
                agentStates: { ...agentStates },
                selectedAgentKey: selectedAgentKey,
                logs: getTerminalLines()
            };
        }

        currentProjectId = projectId;

        if (!lastActivityTimes[projectId]) {
            lastActivityTimes[projectId] = Date.now() / 1000;
        }

        if (!projectStates[projectId]) {
            const initialStates = {};
            Object.keys(agentsData).forEach(key => {
                initialStates[key] = false; // Default: all resting (drunk)
            });
            projectStates[projectId] = {
                agentStates: initialStates,
                selectedAgentKey: "principal-engineer",
                logs: [
                    { type: "system", text: `[System] Switched to Realm: ${projectId}` },
                    { type: "system", text: "[System] Welcome to the Drunken AGY Inn." }
                ]
            };
        }

        const state = projectStates[projectId];
        agentStates = state.agentStates;
        selectedAgentKey = state.selectedAgentKey || "principal-engineer";
        
        restoreTerminalLines(state.logs);

        if (selectedAgentKey) {
            selectAgent(selectedAgentKey);
        } else {
            selectedAgentName.textContent = "Select Party Member";
            selectedAgentModel.textContent = "Job: ---";
            selectedAgentDesc.textContent = "Select a party member to load their character sheet and skills inventory.";
            selectedAgentTools.textContent = "Skills/Tools: ---";
            stateBox.style.display = 'none';
            document.getElementById('jrpg-stats').style.display = 'none';
            terminalTitle.textContent = "Message Window";
            terminalInput.setAttribute('disabled', 'true');
            sendBtn.setAttribute('disabled', 'true');
            terminalInput.placeholder = "Enter input command for party member...";
            
            document.querySelectorAll('.roster-card').forEach(c => c.classList.remove('selected'));
            spriteElements.forEach(s => s.classList.remove('selected'));
        }

        updateIndicators();
        
        // Trigger immediate Discord transceiver status check
        checkDiscordStatus();
    }

    // Load registered project list from server
    async function loadProjects() {
        try {
            const res = await fetch('/api/projects');
            if (res.ok) {
                const projects = await res.json();
                const select = document.getElementById('project-select');
                if (select) {
                    select.innerHTML = '';
                    projects.forEach(p => {
                        const opt = document.createElement('option');
                        opt.value = p.id;
                        opt.textContent = p.name;
                        opt.title = p.name;
                        select.appendChild(opt);
                    });
                    
                    select.removeEventListener('change', handleProjectSelectChange);
                    select.addEventListener('change', handleProjectSelectChange);

                    if (projects.length > 0) {
                        switchProject(projects[0].id);
                    }
                }
            }
        } catch (e) {
            console.error("Failed to load projects list:", e);
            const select = document.getElementById('project-select');
            if (select) {
                select.innerHTML = '<option value="drunken-agy">drunken-agy</option>';
                switchProject("drunken-agy");
            }
        }
    }

    function handleProjectSelectChange(e) {
        switchProject(e.target.value);
    }

    // 3. DOM Elements
    const workingCountBadge = document.getElementById('working-count');
    const drunkCountBadge = document.getElementById('drunk-count');
    const activityBadge = document.getElementById('tavern-activity');
    const toggleAllBtn = document.getElementById('toggle-all-btn');
    
    const spriteElements = document.querySelectorAll('.agent-sprite');
    const rosterGrid = document.getElementById('roster-grid');
    
    const selectedAgentName = document.getElementById('selected-agent-name');
    const selectedAgentModel = document.getElementById('selected-agent-model');
    const selectedAgentDesc = document.getElementById('selected-agent-desc');
    const selectedAgentTools = document.getElementById('selected-agent-tools');
    const stateBox = document.getElementById('state-box');
    const toggleStateBtn = document.getElementById('toggle-state-btn');
    
    const terminalTitle = document.getElementById('terminal-title');
    const terminalBody = document.getElementById('terminal-body');
    const terminalInput = document.getElementById('terminal-input');
    const sendBtn = document.getElementById('send-btn');

    // DOM Elements for Discord Transceiver
    const discordStatusBadge = document.getElementById('discord-status-badge');
    const discordChannelLbl = document.getElementById('discord-channel-lbl');
    const discordConfigBtn = document.getElementById('discord-config-btn');
    const discordToggleBtn = document.getElementById('discord-toggle-btn');
    const configModal = document.getElementById('config-modal');
    const modalTokenInput = document.getElementById('modal-token-input');
    const modalChannelInput = document.getElementById('modal-channel-input');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const modalSaveBtn = document.getElementById('modal-save-btn');

    let discordStatusPollingInterval = null;

    // 4. Update Global Indicators
    function updateIndicators() {
        let workingCount = 0;
        let restingCount = 0;
        
        Object.keys(agentStates).forEach(key => {
            if (agentStates[key]) {
                workingCount++;
            } else {
                restingCount++;
            }
        });
        
        workingCountBadge.textContent = `PARTY ACTIVE: ${workingCount}`;
        drunkCountBadge.textContent = `PARTY DRUNK: ${restingCount}`;
        
        // Calculate Activity
        let activity = "IDLE";
        if (workingCount > 0 && workingCount <= 2) {
            activity = "SCOUTING";
        } else if (workingCount > 2 && workingCount <= 5) {
            activity = "QUESTING";
        } else if (workingCount > 5) {
            activity = "BOSS FIGHT";
        } else if (workingCount === 0) {
            if (restingCount > 5) {
                activity = "DISSOLVED";
            } else {
                activity = "REST INN";
            }
        }
        activityBadge.textContent = `QUEST: ${activity}`;

        // Update sprites classes
        spriteElements.forEach(sprite => {
            const key = sprite.getAttribute('data-agent');
            const isWorking = agentStates[key];
            const bubble = sprite.querySelector('.sprite-bubble');
            
            if (isWorking) {
                sprite.classList.remove('resting');
                sprite.classList.add('working');
                if (bubble) {
                    bubble.textContent = "Locked in!";
                }
            } else {
                sprite.classList.remove('working');
                sprite.classList.add('resting');
                if (bubble) {
                    const speech = agentsData[key].restingSpeech;
                    bubble.textContent = speech.length > 12 ? speech.substring(0, 10) + "..." : speech;
                }
            }
        });

        // Update roster cards (using consistent ACTIVE vs DRUNK status alignment)
        document.querySelectorAll('.roster-card').forEach(card => {
            const key = card.getAttribute('data-agent');
            const isWorking = agentStates[key];
            
            const badge = card.querySelector('.roster-state-badge');
            const hpBar = card.querySelector('.roster-stats .stat-bar.hp');
            const hpValText = card.querySelector('.roster-stats .text-hp');
            
            if (badge) {
                if (isWorking) {
                    badge.className = "roster-state-badge working";
                    badge.textContent = "ACTIVE";
                    if (hpBar) hpBar.style.width = "100%";
                    if (hpValText) hpValText.textContent = "999/999";
                } else {
                    badge.className = "roster-state-badge resting";
                    badge.textContent = "DRUNK";
                    if (hpBar) hpBar.style.width = "12%";
                    if (hpValText) hpValText.textContent = "120/999";
                }
            }
        });
    }

    // 5. Select Agent
    function selectAgent(key) {
        selectedAgentKey = key;
        const agent = agentsData[key];
        if (!agent) {
            console.error("selectAgent error: agent not found for key", key);
            return;
        }
        
        try {
            // Update styling
            document.querySelectorAll('.roster-card').forEach(c => c.classList.remove('selected'));
            const rosterCard = document.querySelector(`.roster-card[data-agent="${key}"]`);
            if (rosterCard) rosterCard.classList.add('selected');
            
            spriteElements.forEach(s => s.classList.remove('selected'));
            if (agent.spriteId) {
                const sprite = document.getElementById(agent.spriteId);
                if (sprite) sprite.classList.add('selected');
            }
            
            // Update Parchment/Blue Panel
            selectedAgentName.textContent = agent.avatar + " " + agent.name;
            selectedAgentModel.textContent = `Job: ${agent.job} | Model: ${agent.model}`;
            selectedAgentDesc.textContent = agent.description;
            selectedAgentTools.textContent = `Skills: ${agent.tools}`;
            
            stateBox.style.display = 'flex';
            const jrpgStats = document.getElementById('jrpg-stats');
            if (jrpgStats) jrpgStats.style.display = 'flex';
            
            try {
                updateSelectedStateDetails();
            } catch (err) {
                console.error("Error in updateSelectedStateDetails:", err);
            }
        } catch (e) {
            console.error("Error updating JRPG agent sheet details:", e);
        }
        
        // Enable Terminal Input (Ensure this runs regardless of JRPG UI rendering state)
        if (terminalTitle) terminalTitle.textContent = `DIALOGUE: ${agent.name}`;
        if (terminalInput) {
            terminalInput.removeAttribute('disabled');
            terminalInput.placeholder = `Talk to ${agent.name} (LV ${agent.lv})...`;
        }
        if (sendBtn) sendBtn.removeAttribute('disabled');

        // Save active agent on the backend
        if (currentProjectId) {
            fetch('/api/project/active-agent', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project_id: currentProjectId, agent_key: key })
            }).catch(err => console.error("Failed to save active agent:", err));
        }
        
        writeToTerminal("system", `[Inspect] Loaded character profile: ${agent.name} [Job: ${agent.job}].`);
    }

    function updateSelectedStateDetails() {
        if (!selectedAgentKey) return;
        
        const isWorking = agentStates[selectedAgentKey];
        const agent = agentsData[selectedAgentKey];
        
        const lvField = document.getElementById('stat-lv');
        const hpBar = document.getElementById('hp-bar');
        const hpTextVal = document.getElementById('stat-hp');
        const statusField = document.getElementById('stat-status-lbl');
        
        if (lvField) lvField.textContent = agent.lv;
        
        if (isWorking) {
            statusField.className = "stat-val status-lbl working";
            statusField.textContent = "ACTIVE";
            if (hpBar) hpBar.style.width = "100%";
            if (hpTextVal) hpTextVal.textContent = "999/999";
            toggleStateBtn.textContent = "REST AT INN";
        } else {
            statusField.className = "stat-val status-lbl resting";
            statusField.textContent = "DRUNK";
            if (hpBar) hpBar.style.width = "12%";
            if (hpTextVal) hpTextVal.textContent = "120/999";
            toggleStateBtn.textContent = "DEPLOY QUEST";
        }
    }

    // 6. Roster Builder
    function buildRoster() {
        rosterGrid.innerHTML = '';
        Object.keys(agentsData).forEach(key => {
            const agent = agentsData[key];
            const card = document.createElement('div');
            card.className = "roster-card";
            card.setAttribute('data-agent', key);
            
            card.innerHTML = `
                <div class="roster-card-header">
                    <div class="roster-info">
                        <h4>${agent.avatar} ${agent.name}</h4>
                        <p>JOB: ${agent.job} | LV ${agent.lv}</p>
                    </div>
                    <span class="roster-state-badge resting">DRUNK</span>
                </div>
                <div class="roster-stats">
                    <div class="roster-stat-row">
                        <span class="roster-stat-lbl">HP:</span>
                        <div class="stat-bar-container">
                            <div class="stat-bar hp" style="width: 12%;"></div>
                        </div>
                        <span class="roster-stat-val text-hp">120/999</span>
                    </div>
                    <div class="roster-stat-row">
                        <span class="roster-stat-lbl">MP:</span>
                        <div class="stat-bar-container">
                            <div class="stat-bar mp" style="width: 100%;"></div>
                        </div>
                        <span class="roster-stat-val">999/999</span>
                    </div>
                </div>
            `;
            
            card.addEventListener('click', () => selectAgent(key));
            rosterGrid.appendChild(card);
        });
    }

    // 7. Write to Terminal
    function writeToTerminal(type, text) {
        const line = document.createElement('div');
        line.className = `terminal-line ${type}`;
        line.textContent = text;
        terminalBody.appendChild(line);
        terminalBody.scrollTop = terminalBody.scrollHeight;
    }

    // Discord API Helper: Check Discord Status for current project
    async function checkDiscordStatus() {
        if (!currentProjectId) return;
        try {
            const res = await fetch(`/api/discord/status?project_id=${currentProjectId}&_=${Date.now()}`);
            if (res.ok) {
                const status = await res.json();
                
                // Update Link Badge
                if (status.is_running) {
                    discordStatusBadge.className = "state-badge working";
                    discordStatusBadge.textContent = "ACTIVE";
                    discordToggleBtn.textContent = "🔌 UNLINK";
                    discordToggleBtn.className = "pixel-btn warning";
                } else {
                    discordStatusBadge.className = "state-badge resting";
                    discordStatusBadge.textContent = "DISCONNECTED";
                    discordToggleBtn.textContent = "⚡ LINK";
                    discordToggleBtn.className = "pixel-btn";
                }

                // Update Channel Label
                if (status.channel_id) {
                    discordChannelLbl.textContent = status.channel_id;
                    discordToggleBtn.removeAttribute('disabled');
                } else {
                    discordChannelLbl.textContent = "None Configured";
                    discordToggleBtn.setAttribute('disabled', 'true');
                }
            }
        } catch (e) {
            console.error("Failed to fetch Discord status:", e);
        }

        // Fetch activity logs
        try {
            const actRes = await fetch(`/api/discord/activity?project_id=${currentProjectId}&_=${Date.now()}`);
            if (actRes.ok) {
                const activities = await actRes.json();
                const lastTime = lastActivityTimes[currentProjectId] || 0;
                let newLastTime = lastTime;
                
                activities.forEach(act => {
                    if (act.timestamp > lastTime) {
                        if (act.type === 'user') {
                            writeToTerminal("system", `[Sys-Discord] ${act.author}: ${act.content}`);
                        } else {
                            writeToTerminal("system", `[Sys-Discord] Response: ${act.content}`);
                        }
                        if (act.timestamp > newLastTime) {
                            newLastTime = act.timestamp;
                        }
                    }
                });
                lastActivityTimes[currentProjectId] = newLastTime;
            }
        } catch (actErr) {
            console.error("Failed to fetch Discord activity:", actErr);
        }

        // Fetch project agy running status
        try {
            const agyRes = await fetch(`/api/project/status?project_id=${currentProjectId}&_=${Date.now()}`);
            if (agyRes.ok) {
                const agyStatus = await agyRes.json();
                const wasRunning = document.body.classList.contains('agy-running');
                
                if (agyStatus.agy_running) {
                    document.body.classList.add('agy-running');
                    // Automatically put all agents in working state if they weren't already
                    let updated = false;
                    Object.keys(agentStates).forEach(key => {
                        if (!agentStates[key]) {
                            agentStates[key] = true;
                            updated = true;
                        }
                    });
                    if (!wasRunning) {
                        writeToTerminal("system", `[Realm] Active agy process detected in VS Code / terminal for "${currentProjectId}"! Party set to QUEST mode.`);
                    }
                    if (updated) {
                        updateIndicators();
                        updateSelectedStateDetails();
                    }
                } else {
                    document.body.classList.remove('agy-running');
                    if (wasRunning) {
                        // Automatically put all agents back to resting state
                        Object.keys(agentStates).forEach(key => {
                            agentStates[key] = false;
                        });
                        writeToTerminal("system", `[Realm] Agy process completed for "${currentProjectId}". Party returned to Inn to rest and drink.`);
                        updateIndicators();
                        updateSelectedStateDetails();
                    }
                }
            }
        } catch (agyErr) {
            console.error("Failed to fetch project status:", agyErr);
        }
    }

    // Start Polling Discord Status
    function startDiscordPolling() {
        if (discordStatusPollingInterval) clearInterval(discordStatusPollingInterval);
        checkDiscordStatus();
        discordStatusPollingInterval = setInterval(checkDiscordStatus, 3000);
    }

    // 8. Event Listeners
    // Sprite Clicks
    spriteElements.forEach(sprite => {
        sprite.addEventListener('click', () => {
            const key = sprite.getAttribute('data-agent');
            selectAgent(key);
        });
    });

    // Toggle Individual Agent State
    toggleStateBtn.addEventListener('click', () => {
        if (!selectedAgentKey) return;
        const currentState = agentStates[selectedAgentKey];
        const nextState = !currentState;
        agentStates[selectedAgentKey] = nextState;
        
        const agent = agentsData[selectedAgentKey];
        if (nextState) {
            writeToTerminal("system", `[System] Command received. ${agent.name} deployed to quest.`);
            // Simulate agent transition logs
            agent.workingLogs.forEach((log, index) => {
                setTimeout(() => {
                    if (agentStates[selectedAgentKey] === true) { // check if still working
                        writeToTerminal("system", log);
                    }
                }, (index + 1) * 600);
            });
        } else {
            writeToTerminal("system", `[System] ${agent.name} returned to Inn to recover HP/MP.`);
            agent.restingLogs.forEach((log, index) => {
                setTimeout(() => {
                    if (agentStates[selectedAgentKey] === false) { // check if still resting
                        writeToTerminal("system", log);
                    }
                }, (index + 1) * 600);
            });
        }
        
        updateSelectedStateDetails();
        updateIndicators();
    });

    // Ring Inn Bell (Toggle All)
    toggleAllBtn.addEventListener('click', () => {
        const anyResting = Object.values(agentStates).some(state => state === false);
        
        Object.keys(agentStates).forEach(key => {
            agentStates[key] = anyResting;
        });
        
        if (anyResting) {
            writeToTerminal("system", "🔔 *CLANG CLANG*! The Inn bell rings! All party members equip gear and prepare for battle!");
            Object.keys(agentsData).forEach(key => {
                const agent = agentsData[key];
                if (Math.random() > 0.4) {
                    writeToTerminal("system", agent.workingLogs[0]);
                }
            });
        } else {
            writeToTerminal("system", "🔔 *CLANG CLANG*! The Inn bell rings! Quest complete. The party goes to rest and orders pints of mead!");
            Object.keys(agentsData).forEach(key => {
                const agent = agentsData[key];
                if (Math.random() > 0.4) {
                    writeToTerminal("system", agent.restingLogs[0]);
                }
            });
        }
        
        if (selectedAgentKey) {
            updateSelectedStateDetails();
        }
        updateIndicators();
    });

    // Chat Command Execution
    async function handleSend() {
        const text = terminalInput.value.trim();
        if (!text || !selectedAgentKey) return;
        
        writeToTerminal("user", `You: ${text}`);
        terminalInput.value = '';
        
        const agent = agentsData[selectedAgentKey];
        const isWorking = agentStates[selectedAgentKey];
        const agentStatus = isWorking ? "ACTIVE" : "DRUNK";
        
        writeToTerminal("system", `[${agent.name}] casting prompt response...`);
        
        try {
            const res = await fetch('/api/terminal/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: currentProjectId,
                    command: text,
                    agent: selectedAgentKey,
                    status: agentStatus
                })
            });
            
            if (res.ok) {
                const data = await res.json();
                writeToTerminal("system", `[${agent.name}]: ${data.output}`);
            } else {
                const err = await res.json();
                writeToTerminal("error", `[Error] Command failed: ${err.error}`);
            }
        } catch (e) {
            writeToTerminal("error", `[Error] Network error: ${e}`);
        }
    }

    sendBtn.addEventListener('click', handleSend);
    terminalInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            handleSend();
        }
    });

    // Discord Config Form Triggers
    discordConfigBtn.addEventListener('click', () => {
        modalTokenInput.value = '';
        modalChannelInput.value = discordChannelLbl.textContent === "None Configured" ? "" : discordChannelLbl.textContent;
        configModal.style.display = 'flex';
    });

    modalCancelBtn.addEventListener('click', () => {
        configModal.style.display = 'none';
    });

    modalSaveBtn.addEventListener('click', async () => {
        const token = modalTokenInput.value.trim();
        const channelId = modalChannelInput.value.trim();

        if (!channelId) {
            writeToTerminal("error", "[Error] Room ID is required to link.");
            return;
        }

        try {
            const res = await fetch('/api/discord/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: currentProjectId,
                    bot_token: token || null,
                    channel_id: channelId
                })
            });

            if (res.ok) {
                configModal.style.display = 'none';
                writeToTerminal("system", `[System] Transceiver configuration updated for Realm.`);
                checkDiscordStatus();
            } else {
                const err = await res.json();
                writeToTerminal("error", `[Error] Config failed: ${err.error}`);
            }
        } catch (e) {
            writeToTerminal("error", `[Error] Network error during config: ${e}`);
        }
    });

    // Toggle Discord process link
    discordToggleBtn.addEventListener('click', async () => {
        const isActive = discordStatusBadge.textContent === "ACTIVE";
        const endpoint = isActive ? '/api/discord/stop' : '/api/discord/start';
        const systemMsg = isActive ? 
            "[System] Transceiver deactivated. Discord listener terminated." : 
            "[System] Transceiver activated. Launching Discord command listener...";

        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project_id: currentProjectId })
            });

            if (res.ok) {
                writeToTerminal("system", systemMsg);
                checkDiscordStatus();
            } else {
                const err = await res.json();
                writeToTerminal("error", `[Error] Transceiver error: ${err.error}`);
            }
        } catch (e) {
            writeToTerminal("error", `[Error] Transceiver request failed: ${e}`);
        }
    });

    // 9. Boot Init
    buildRoster();
    loadProjects();
    startDiscordPolling();
});
