"""
RSS feeds organized by theme. Edit freely — add, remove, reorganize.
Dead feeds are skipped silently at fetch time.
"""

FEEDS = {
    "ai_education": [
        "https://hechingerreport.org/feed/",
        "https://www.edsurge.com/articles_rss",
        "https://www.the74million.org/feed/",
        "https://hai.stanford.edu/news/rss.xml",
        "https://www.brookings.edu/topic/education/feed/",
        "https://www.insidehighered.com/rss.xml",
    ],
    "innovation_education": [
        "https://www.gettingsmart.com/feed/",
        "https://www.christenseninstitute.org/feed/",
        "https://www.educationnext.org/feed/",
        "https://www.kqed.org/mindshift/feed",
        "https://hechingerreport.org/feed/",  # overlap is fine; dedup is by URL
    ],
    "arts_education": [
        "https://www.edutopia.org/rss.xml",
        "https://www.americansforthearts.org/news/feed",
        "https://www.artsedsearch.org/feed/",
    ],
    "human_flourishing": [
        "https://greatergood.berkeley.edu/feeds",
        "https://characterlab.org/feed/",
        "https://www.mindshift.kqed.org/feed",
    ],
    # Wide-net intellectual magazines and think tanks. These publish on many
    # topics; the ranker is told to deprioritize non-education pieces, so most
    # noise gets filtered. Worth the false positives for the occasional gem.
    "big_picture": [
        "https://nautil.us/feed/",
        "https://aeon.co/feed.rss",
        "https://api.quantamagazine.org/feed/",
        "https://www.noemamag.com/feed/",                          # Berggruen — strong on AI + governance + philosophy
        "https://www.santafe.edu/news-center/news/feed",           # complexity / systems
        "https://blog.longnow.org/feed/",                          # long-arc thinking
        "https://www.aspeninstitute.org/feed/",                    # broad; ranker filters
        "https://www.newamerica.org/feed/",                        # policy think tank
        "https://www.themarginalian.org/feed/",                    # Maria Popova — humanities
        "https://fs.blog/feed/",                                   # Farnam Street — thinking/learning
        "https://www.worksinprogress.co/feed/",
        "https://asteriskmag.com/feed",                            # rationalist-adjacent big questions
    ],
    # International / comparative / systems-level education
    "international": [
        "https://oecdedutoday.com/feed/",                          # OECD Education
        "https://theconversation.com/us/topics/education-117/articles.atom",
        "https://blogs.worldbank.org/en/education/rss.xml",
        "https://www.tes.com/magazine/rss",                        # UK perspective
        "https://www.ucl.ac.uk/ioe/news/rss.xml",                  # UCL Institute of Education
        "https://www.bera.ac.uk/feed",                             # British Educational Research Assoc
    ],
    # Practitioner-level: actual teachers, students, innovative schools.
    # The counterweight to policy/theory/doom — concrete stories of what's working.
    "practitioner_stories": [
        "https://www.cultofpedagogy.com/feed/",                    # Jennifer Gonzalez
        "https://www.weareteachers.com/feed/",
        "https://larryferlazzo.edublogs.org/feed/",                # Larry Ferlazzo
        "https://hthunboxed.org/feed/",                            # High Tech High publication
        "https://www.bigpicture.org/feed/",                        # Big Picture Learning network
        "https://eleducation.org/news-and-events/feed",            # EL Education
        "https://xqsuperschool.org/feed/",                         # XQ Institute
        "https://transcendeducation.org/feed/",                    # Transcend
        "https://scienceleadership.org/feed",                      # SLA (Philadelphia)
        "https://workshopschool.org/feed/",                        # Workshop School (Philadelphia)
    ],
}

# Themes Claude uses to score articles. Refine the language here over time —
# this is the single biggest lever for what your newsletter "feels like."
THEMES = """
1. AI's impact on education — pedagogy shifts, student tool use, policy, equity, teacher workflows, assessment in an AI world
2. Innovation in education — new school models, project-based learning, assessment redesign, microschools, alt-credentials, learning sciences
3. Visual and performing arts in education — arts integration, creative practice in schools, arts pedagogy, maker culture, design education
4. Human flourishing in education — student wellbeing, character, meaning, purpose, mental health, relational pedagogy
5. Futures & philosophy of education — systems-level and complexity views of learning; international and comparative education; the philosophy and changing purpose/role of schools; structural redesign of educational systems; long-arc and big-idea thinking about what education is *for* (Santa Fe / Aspen / Nautilus / Noema register)
"""

# Story qualities to actively favor — biases the ranker upward, the counterweight
# to DEPRIORITIZE. The goal isn't "happier news," it's giving credit for
# concreteness, real people, and demonstrable practice.
PRIORITIZE = """
- Concrete practitioner stories: named teachers, students, projects, schools doing the actual work (High Tech High, Big Picture Learning, EL Education, Science Leadership Academy, Workshop School, XQ schools, etc.)
- Original reporting with named people and named places — not just trends, frameworks, or commentary
- Pieces that surface what's *working* and worth modeling, not only what's broken
- First-person teacher or student voice, especially from classrooms doing project-based, arts-integrated, or interdisciplinary work
- Stories that connect big ideas (the Nautilus/Noema register) to actual practice
"""

# Story types to deprioritize. Helps Claude filter out noise.
DEPRIORITIZE = """
- Vendor PR / product announcements with no pedagogical substance
- Generic "back to school" or seasonal content
- Pure local school-board politics unless nationally significant
- Sports / athletics stories
- Listicles without original reporting
- Pure-science or general-interest pieces from the big_picture feeds that don't connect to learning, education, schools, or the cultivation of minds (these feeds publish on many topics; only score education-adjacent pieces highly)
- "Feel-good" filler with no specific practice, person, or insight — concrete > inspirational
"""
