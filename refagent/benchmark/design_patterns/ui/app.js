let candidates = [];
let pendingUpdates = new Set();

const listEl = document.getElementById('candidate-list');
const loadingEl = document.getElementById('loading');
const remainingCountEl = document.getElementById('remaining-count');
const validatedCountEl = document.getElementById('validated-count');
const updateBtn = document.getElementById('update-btn');
const searchInput = document.getElementById('search');

async function fetchData() {
    loadingEl.classList.remove('hidden');
    listEl.innerHTML = '';
    try {
        const res = await fetch('/api/candidates');
        candidates = await res.json();
        render();
    } catch (err) {
        console.error(err);
        loadingEl.innerText = 'Failed to load data.';
    } finally {
        loadingEl.classList.add('hidden');
    }
}

function render() {
    const query = searchInput.value.toLowerCase();
    
    // items are "reviewed" if the server says so OR if we just reviewed them in this session
    const filtered = candidates.filter(c => {
        const match = c.pattern.toLowerCase().includes(query) || c.class_name.toLowerCase().includes(query);
        return match && (!c.reviewed || pendingUpdates.has(c.id));
    });

    remainingCountEl.innerText = candidates.filter(c => !c.reviewed && !pendingUpdates.has(c.id)).length;
    validatedCountEl.innerText = candidates.filter(c => c.reviewed || pendingUpdates.has(c.id)).length;
    
    listEl.innerHTML = filtered.map(c => {
        const isPending = pendingUpdates.has(c.id);
        const currentVal = c.human_validation;
        
        return `
            <div class="candidate-card ${c.reviewed ? 'card-reviewed' : ''}" id="card-${c.id}">
                <div class="candidate-info">
                    <div class="candidate-header">
                        <div class="pattern-group">
                            <span class="pattern-badge">${c.pattern}</span>
                            <span class="repo-name">${c.repo_path.split('/').pop()}</span>
                        </div>
                        <div class="selection-group">
                            <button class="btn btn-accept ${currentVal === true ? 'active' : ''}" 
                                onclick="setReview('${c.id}', true, '${c.birth_commit_url}')">Accept</button>
                            <button class="btn btn-reject ${currentVal === false && isPending ? 'active' : ''}" 
                                onclick="setReview('${c.id}', false, '${c.birth_commit_url}')">Reject</button>
                        </div>
                    </div>
                    <div class="class-name">${c.class_name}</div>
                    <div class="reasoning">${c.detection_reasoning || 'No reasoning provided.'}</div>
                    <a href="${c.birth_commit_url}" target="_blank" class="view-commit">
                        View Birth Commit ↗
                    </a>
                </div>
            </div>
        `;
    }).join('');

    updateBtn.innerText = `Update Files (${pendingUpdates.size})`;
    updateBtn.disabled = pendingUpdates.size === 0;
}

window.setReview = (id, accept, url) => {
    const candidate = candidates.find(c => c.id === id);
    const wasPending = pendingUpdates.has(id);
    
    candidate.human_validation = accept;
    pendingUpdates.add(id);
    
    // Open URL in new tab ONLY if it's the first time we touch this item in this session
    if (!wasPending && url && url !== '#') {
        window.open(url, '_blank');
    }
    
    render();
};

updateBtn.onclick = async () => {
    const updates = Array.from(pendingUpdates).map(id => {
        const c = candidates.find(item => item.id === id);
        return { 
            id: c.id, 
            human_validation: c.human_validation,
            reviewed: true 
        };
    });

    updateBtn.innerText = 'Updating...';
    updateBtn.disabled = true;

    try {
        const res = await fetch('/api/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        
        if (res.ok) {
            pendingUpdates.clear();
            // Refresh to hide the newly reviewed items
            fetchData();
        } else {
            alert('Failed to update file.');
        }
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        render();
    }
};

searchInput.oninput = render;
document.getElementById('refresh-btn').onclick = fetchData;

fetchData();
