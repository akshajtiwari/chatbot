
        function createParticles() {
            const container = document.getElementById('particles');
            let particleCount = 50;
            if (window.innerWidth < 600) particleCount = 20;
            for (let i = 0; i < particleCount; i++) {
                const particle = document.createElement('div');
                particle.className = 'particle';
                particle.style.left = Math.random() * 100 + '%';
                particle.style.animationDelay = Math.random() * 6 + 's';
                particle.style.animationDuration = (6 + Math.random() * 4) + 's';
                container.appendChild(particle);
            }
        }

        const body = document.body;
        const accessibilitySelect = document.getElementById('accessibilitySelect');

        function setTheme(theme) {
            body.classList.remove('theme-dark', 'theme-hc', 'theme-lc');
            
            if (theme !== 'light') {
                body.classList.add(`theme-${theme}`);
            }
            
            accessibilitySelect.value = theme;
            
            localStorage.setItem('campus-theme', theme);
        }

        accessibilitySelect.addEventListener('change', (e) => {
            setTheme(e.target.value);
        });

        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });

        const observerOptions = {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.style.animationPlayState = 'running';
                }
            });
        }, observerOptions);

        document.querySelectorAll('.feature-card, .stat-item, .language-badge').forEach(el => {
            observer.observe(el);
        });

        const savedTheme = localStorage.getItem('campus-theme') || 'light';
        setTheme(savedTheme);

        createParticles();

        window.addEventListener('scroll', () => {
            const navbar = document.querySelector('.accessibility-bar');
            if (window.scrollY > 100) {
                navbar.style.background = body.classList.contains('theme-dark') 
                    ? 'rgba(10, 10, 11, 0.98)' 
                    : 'rgba(255, 255, 255, 0.98)';
            } else {
                navbar.style.background = body.classList.contains('theme-dark') 
                    ? 'rgba(10, 10, 11, 0.95)' 
                    : 'rgba(255, 255, 255, 0.95)';
            }
        });

        document.querySelectorAll('.feature-card').forEach(card => {
            card.addEventListener('mouseenter', function() {
                this.style.transform = 'translateY(-12px) scale(1.02)';
            });
            
            card.addEventListener('mouseleave', function() {
                this.style.transform = 'translateY(0) scale(1)';
            });
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                document.body.classList.add('keyboard-nav');
            }
        });

        document.addEventListener('mousedown', () => {
            document.body.classList.remove('keyboard-nav');
        });