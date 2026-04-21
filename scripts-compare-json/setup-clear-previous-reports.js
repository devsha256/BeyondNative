// This function gets all active collection variables and returns them as a key-value object.
const getActiveVariables = () => {
    // pm.collectionVariables.values is a property that returns an array of variable objects.
    const allVarsArray = pm.collectionVariables.values; 
    return allVarsArray.reduce((vars, variable) => {
        vars[variable.key] = variable.value;
        return vars;
    }, {});
};

// Generates an HTML list from an array of variables.
const generateVariableList = (vars) => {
    if (!vars || vars.length === 0) {
        return '<li>No variables were preserved.</li>';
    }
    return vars.map(v => `<li>${v}</li>`).join('');
};

// Defines the CSS for the visualizer.
const getCSS = () => `
    :root {
        --md-sys-color-primary: #6750A4;
        --md-sys-color-surface: #FFFFFF;
        --md-sys-color-surface-variant: #F0F0F0;
        --md-sys-color-on-surface: #1C1B1F;
        --md-sys-color-on-surface-variant: #49454F;
        --md-sys-color-outline: #CCCCCC;
        --border-radius: 12px;
        --spacing-small: 8px;
        --spacing-medium: 16px;
        --spacing-large: 24px;
    }

    body {
        background-color: var(--md-sys-color-surface);
        font-family: 'Roboto', Arial, sans-serif;
        font-size: 14px;
        color: var(--md-sys-color-on-surface);
        padding: var(--spacing-large);
        margin: 0;
        box-sizing: border-box;
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        text-align: center;
    }

    .container {
        max-width: 560px;
        width: 100%;
        padding: var(--spacing-large);
        background: transparent;
        box-shadow: none;
    }

    h2 {
        color: var(--md-sys-color-primary);
        font-size: 22px;
        font-weight: 500;
        margin-bottom: var(--spacing-medium);
    }

    .stats, .preserved {
        background-color: var(--md-sys-color-surface-variant);
        padding: var(--spacing-medium);
        border-radius: var(--border-radius);
        color: var(--md-sys-color-on-surface-variant);
        margin-top: var(--spacing-medium);
    }

    .stats p {
        margin: var(--spacing-small) 0;
    }

    .preserved {
        text-align: left;
        max-height: 250px;
        overflow-y: auto;
    }

    .preserved h3 {
        font-size: 16px;
        font-weight: 500;
        margin-bottom: var(--spacing-medium);
        color: var(--md-sys-color-on-surface-variant);
    }

    .preserved ul {
        list-style: none;
        padding: 0;
    }

    .preserved li {
        padding: 8px;
        border-bottom: 1px solid var(--md-sys-color-outline);
        font-size: 13px;
    }

    .preserved li:last-child {
        border-bottom: none;
    }

    .signature {
        font-size: 12px;
        color: var(--md-sys-color-on-surface-variant);
        font-style: italic;
        margin-top: var(--spacing-large);
    }
    
    svg#bubble-animation {
        width: 100%;
        height: 180px;
        margin-top: var(--spacing-medium);
        background-color: var(--md-sys-color-surface-variant);
        border-radius: var(--border-radius);
    }
`;

// Generates the complete HTML for the visualizer.
const generateHTML = (clearedReports, clearedTemp, preservedVars) => {
    const varList = generateVariableList(preservedVars);
    const style = getCSS();
    
    return `<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500&display=swap" rel="stylesheet">
        <style>${style}</style>
        <script src="https://d3js.org/d3.v7.min.js"></script>
        <title>Setup Complete</title>
    </head>
    <body>
        <div class="container">
            <h2>Setup Complete</h2>
            <svg id="bubble-animation"></svg>
            <div class="stats">
                <p>Cleared <strong>${clearedReports}</strong> previous report entries.</p>
                <p>Cleared <strong>${clearedTemp}</strong> temporary variables.</p>
            </div>
            <div class="preserved">
                <h3>Preserved Variables (${preservedVars.length})</h3>
                <ul>${varList}</ul>
            </div>
            <div class="signature">S. 2025</div>
        </div>

        <script>
            const svg = d3.select('#bubble-animation');
            const width = svg.node().getBoundingClientRect().width;
            const height = svg.node().getBoundingClientRect().height;
            const centerX = width / 2;
            const centerY = height / 2;

            const numBubbles = Math.min(${clearedTemp}, 20); // Cap at 20 bubbles for performance

            if (numBubbles > 0) {
                const bubbles = d3.range(numBubbles).map(() => ({}));

                const bubbleElements = svg.selectAll('circle')
                    .data(bubbles)
                    .join('circle')
                    .attr('cx', centerX)
                    .attr('cy', centerY)
                    .attr('r', 0)
                    .attr('fill', 'var(--md-sys-color-primary)')
                    .style('opacity', 0.7);

                function animate(selection) {
                    selection.transition()
                        .delay((d, i) => i * 200) // Stagger the start of each bubble
                        .duration(3000)
                        .attr('r', Math.min(width, height) / 2)
                        .style('opacity', 0)
                        .on('end', function() {
                            // Reset the bubble to start again
                            d3.select(this)
                                .attr('r', 0)
                                .style('opacity', 0.7);
                            animate(d3.select(this)); // Restart the animation for this bubble
                        });
                }
                
                animate(bubbleElements);
            }
        </script>
    </body>
    </html>`;
};

// --- Main Execution ---
const activeVars = getActiveVariables();
const previousCount = parseInt(activeVars["report_request_count"] || "0");

let userPreservedVars = [];
if (activeVars["variables"]) {
    try {
        userPreservedVars = JSON.parse(activeVars["variables"]);
    } catch (e) {
        console.error("Could not parse 'variables'. Please ensure it's a valid JSON array.");
    }
}

const systemVars = [
    "mule_base_url", "boomi_base_url", "exempted_fields", "boomi_auth_type",
    "boomi_username", "boomi_password", "boomi_bearer_token", "boomi_api_key",
    "boomi_api_key_header", "variables"
];

const allPreservedKeys = [...new Set(systemVars.concat(userPreservedVars))];
const finalPreservedVars = allPreservedKeys.filter(key => activeVars.hasOwnProperty(key));

// Clear reports
let clearedReports = 0;
for (let i = 1; i <= previousCount; i++) {
    const varName = "report_data_" + i.toString().padStart(3, '0');
    if (activeVars.hasOwnProperty(varName)) {
        pm.collectionVariables.unset(varName);
        clearedReports++;
    }
}

// Clear temporary variables
const tempVars = [
    "report_request_count", "current_report_index", "temp_request_name",
    "temp_request_curl", "boomi_response", "boomi_status", "boomi_error",
    "csv_full_report", "csv_summary_report",
    "regression_mode", "regression_curl", "regression_request_name"
];

let clearedTemp = 0;
for (const varName of tempVars) {
    if (activeVars.hasOwnProperty(varName) && !finalPreservedVars.includes(varName)) {
        pm.collectionVariables.unset(varName);
        clearedTemp++;
    }
}

pm.collectionVariables.set("report_request_count", "0");

const html = generateHTML(clearedReports, clearedTemp, finalPreservedVars);
pm.visualizer.set(html);
