/**
 * Resume Ranking Dashboard - Frontend JavaScript
 * Handles API calls and UI rendering with Premium Glassmorphism Effects
 */

class ResumeRankingApp {
    constructor() {
        this.apiEndpoint = '/api';
        this.initEventListeners();
        console.log('Resume Ranking AI: Initialized');
    }

    initEventListeners() {
        // Single resume analysis
        document.getElementById('analyzeBtn')?.addEventListener('click', () => this.analyzeResume());

        // Batch ranking
        document.getElementById('rankBtn')?.addEventListener('click', () => this.rankCandidates());

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                if (e.key === 'Enter') {
                    // Only trigger if a text area is focused or if it's a general command
                    this.analyzeResume();
                }
            }
        });
    }

    /**
     * Analyze a single resume
     */
    async analyzeResume() {
        const resumeText = document.getElementById('resumeText')?.value?.trim();
        const jobDescription = document.getElementById('jobDescription')?.value?.trim() || '';
        const useAI = document.getElementById('useAI')?.checked || false;
        const button = document.getElementById('analyzeBtn');
        const container = document.getElementById('resultsContainer');

        if (!resumeText) {
            this.showError(container, 'Please enter resume text to proceed.');
            return;
        }

        // Show loading state
        button.disabled = true;
        button.innerHTML = '<span class="loading-spinner"></span> Processing...';
        container.innerHTML = `
            <div class="loading">
                Analyzing expertise, matching patterns, and calculating scores...
            </div>
        `;

        try {
            const response = await fetch(`${this.apiEndpoint}/analyze`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    resume_text: resumeText,
                    job_description: jobDescription,
                    use_ai: useAI
                })
            });

            const result = await response.json();

            if (result.success) {
                this.renderResult(container, result.data);
            } else {
                this.showError(container, result.error || 'Analysis failed');
            }

        } catch (error) {
            console.error('Analysis error:', error);
            if (error instanceof TypeError) {
                this.showError(container, 'Data rendering error. The AI response might be missing some fields.');
            } else {
                this.showError(container, 'Network or server error. Please try again.');
            }
        } finally {
            button.disabled = false;
            button.textContent = 'Analyze Candidate';
        }
    }

    /**
     * Rank multiple candidates
     */
    async rankCandidates() {
        const batchDataStr = document.getElementById('batchData')?.value?.trim();
        const button = document.getElementById('rankBtn');
        const container = document.getElementById('rankingTable');

        let candidates;
        try {
            candidates = JSON.parse(batchDataStr);
        } catch (e) {
            this.showError(container, 'Invalid JSON format. Please verify your input syntax.', true);
            return;
        }

        if (!Array.isArray(candidates) || candidates.length === 0) {
            this.showError(container, 'Please provide a non-empty array of candidate objects.', true);
            return;
        }

        // Show loading state
        button.disabled = true;
        button.textContent = 'Ranking Candidates...';
        container.innerHTML = '<div class="loading">Batch processing candidates...</div>';

        try {
            const response = await fetch(`${this.apiEndpoint}/ranking`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ candidates })
            });

            const result = await response.json();

            if (result.success) {
                this.renderRankingTable(container, result.data);
            } else {
                this.showError(container, result.error || 'Ranking failed', true);
            }

        } catch (error) {
            this.showError(container, 'Network error. Please try again.', true);
        } finally {
            button.disabled = false;
            button.textContent = 'Run Batch Ranking Algorithm';
        }
    }

    /**
     * Render single analysis result with Premium UI
     */
    renderResult(container, data) {
        const scoreClass = this.getScoreClass(data.final_rank_score);

        container.innerHTML = `
            <div class="result-card">
                <div class="result-header">
                    <div>
                         <div class="result-name">${this.escapeHtml(data.name)}</div>
                         <div style="font-size: 0.9rem; color: var(--text-muted);">${this.escapeHtml(data.university)}</div>
                    </div>
                    <div class="result-score ${scoreClass}">${data.final_rank_score.toFixed(1)}</div>
                </div>
                
                <div class="result-details">
                    <div class="detail-item">
                        <div class="detail-label">University Tier</div>
                        <div class="detail-value">${data.uni_tier_score}/10</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Python Mastery</div>
                        <div class="detail-value">${data.python_score}/10</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Experience</div>
                        <div class="detail-value">${data.python_experience_years} Years</div>
                    </div>
                </div>

                <div class="evidence-quote">
                    <strong style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.5rem;">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        Key Evidence Detected
                    </strong>
                    "${this.escapeHtml(data.evidence_quote)}"
                </div>
            </div>
        `;
    }

    /**
     * Render ranking table for multiple candidates
     */
    renderRankingTable(container, rankings) {
        if (rankings.length === 0) {
            container.innerHTML = '<p class="placeholder">No candidates to display</p>';
            return;
        }

        let html = `
            <table>
                <thead>
                    <tr>
                        <th style="width: 60px;">Rank</th>
                        <th>Candidate Profile</th>
                        <th style="width: 100px;">Uni Tier</th>
                        <th style="width: 100px;">Python</th>
                        <th style="width: 100px;">Exp (Yrs)</th>
                        <th style="width: 200px;">Final Score</th>
                    </tr>
                </thead>
                <tbody>
        `;

        rankings.forEach((candidate, index) => {
            const rank = index + 1;
            const rankClass = rank <= 3 ? `rank-${rank}` : 'rank-other';
            const scoreClass = this.getScoreClass(candidate.final_rank_score);
            const scorePercent = (candidate.final_rank_score / 10) * 100;

            html += `
                <tr>
                    <td>
                        <div class="rank-badge ${rankClass}">${rank}</div>
                    </td>
                    <td>
                        <div style="font-weight:700; color:white;">${this.escapeHtml(candidate.name)}</div>
                        <div style="font-size:0.8rem; color:var(--text-muted);">${this.escapeHtml(candidate.university)}</div>
                    </td>
                    <td><span style="font-family:monospace; font-weight:bold;">${candidate.uni_tier_score}</span></td>
                    <td><span style="font-family:monospace; font-weight:bold;">${candidate.python_score}</span></td>
                    <td>${candidate.python_experience_years}</td>
                    <td>
                        <div class="score-bar">
                            <div class="score-bar-fill" style="width: ${scorePercent}%"></div>
                        </div>
                        <div style="text-align:right; font-size:0.8rem; margin-top:0.2rem;" class="${scoreClass}">
                            ${candidate.final_rank_score.toFixed(2)} / 10.0
                        </div>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    }

    /**
     * Get color class based on score
     */
    getScoreClass(score) {
        if (score >= 8) return 'score-high';
        if (score >= 5) return 'score-medium';
        return 'score-low';
    }

    /**
     * Show error message
     * @param {HTMLElement} container 
     * @param {string} message 
     * @param {boolean} isBatch 
     */
    showError(container, message, isBatch = false) {
        container.innerHTML = `
            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid var(--danger); color: #fca5a5; padding: 1rem; border-radius: 8px;">
                <strong>Error:</strong> ${this.escapeHtml(message)}
            </div>
        `;
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ResumeRankingApp();
});
