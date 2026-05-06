document.addEventListener('DOMContentLoaded', function() {
    const queryForm = document.getElementById('query-form');
    const queryInput = document.getElementById('query-input');
    const domainSelect = document.getElementById('domain-select');
    const responseArea = document.getElementById('response-area');
    const answerDiv = document.getElementById('answer');
    const helpfulBtn = document.getElementById('helpful-btn');
    const notHelpfulBtn = document.getElementById('not-helpful-btn');
    const insightToggle = document.getElementById('insight-toggle');
    const insightPanel = document.getElementById('insight-panel');
    const roleToneSpan = document.getElementById('role-tone');
    const enginesSpan = document.getElementById('engines');
    const explanationsUl = document.getElementById('explanations');
    const actionsUl = document.getElementById('actions');
    const lastBatchSpan = document.getElementById('last-batch');
    const learnedRulesSpan = document.getElementById('learned-rules');
    const sandboxModeSpan = document.getElementById('sandbox-mode');

    let currentEventId = null;

    queryForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        const query = queryInput.value.trim();
        const domain = domainSelect.value;
        const modeMap = { sysops: 'auto', gm: 'auto', assistant: 'cognitive', legal: 'rag' };
        const mode = modeMap[domain] || 'auto';
        if (!query) return;

        try {
            const response = await fetch('/api/v1/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: query,
                    mode,
                    character: 'synth',
                    include_debug: true
                })
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const data = await response.json();
            answerDiv.textContent = data.response || '';
            roleToneSpan.textContent = `${data.character || 'synth'}/${data.source || 'unknown'}`;
            enginesSpan.textContent = data.source || 'unknown';
            currentEventId = data.session_id || null;

            // Clear and populate explanations
            explanationsUl.innerHTML = '';
            (data.debug?.explanations || []).forEach(exp => {
                const li = document.createElement('li');
                li.textContent = exp;
                explanationsUl.appendChild(li);
            });

            // Clear and populate actions
            actionsUl.innerHTML = '';
            (data.debug?.actions_taken || []).forEach(action => {
                const li = document.createElement('li');
                li.textContent = `${action.action}: ${JSON.stringify(action)}`;
                actionsUl.appendChild(li);
            });

            // Legacy panel fallback values (not part of v1 query payload)
            lastBatchSpan.textContent = 'N/A';
            learnedRulesSpan.textContent = 'N/A';
            sandboxModeSpan.textContent = 'N/A';

            responseArea.style.display = 'block';
        } catch (error) {
            console.error('Error:', error);
            answerDiv.textContent = 'An error occurred while processing your query.';
            responseArea.style.display = 'block';
        }
    });

    helpfulBtn.addEventListener('click', async function() {
        if (currentEventId !== null) {
            await sendFeedback(currentEventId, 'helpful');
        }
    });

    notHelpfulBtn.addEventListener('click', async function() {
        if (currentEventId !== null) {
            await sendFeedback(currentEventId, 'not_helpful');
        }
    });

    insightToggle.addEventListener('click', function() {
        if (insightPanel.style.display === 'none') {
            insightPanel.style.display = 'block';
            insightToggle.textContent = 'Hide Reasoning Details';
        } else {
            insightPanel.style.display = 'none';
            insightToggle.textContent = 'Show Reasoning Details';
        }
    });

    async function sendFeedback(eventId, feedbackType) {
        try {
            const response = await fetch('/api/feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    event_id: eventId,
                    feedback_type: feedbackType
                })
            });

            if (response.ok) {
                alert('Feedback submitted successfully!');
            } else {
                alert('Failed to submit feedback.');
            }
        } catch (error) {
            console.error('Feedback error:', error);
            alert('An error occurred while submitting feedback.');
        }
    }
});
