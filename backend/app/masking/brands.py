"""Known brands, merchants and institutions. Their names are kept by the masker because they carry
the category (SWIGGY means food delivery). Businesses are not personal data.

Matching is case-insensitive on whole words; multi-word brands match as a phrase. Add to this list
when the Masked column shows a well-known merchant as [NAME_…].
"""

BRANDS: tuple[str, ...] = (
    # Food & dining
    "swiggy", "zomato", "dominos", "domino's", "mcdonalds", "mcdonald's", "kfc", "burger king", "pizza hut", "subway",
    "starbucks", "cafe coffee day", "ccd", "chai point", "chaayos", "barbeque nation", "faasos", "behrouz", "eatsure",
    "box8", "haldirams", "haldiram's", "bikanervala", "wow momo", "theobroma", "third wave coffee", "blue tokai",
    # Groceries
    "bigbasket", "blinkit", "grofers", "zepto", "instamart", "swiggy instamart", "dmart", "avenue supermarts",
    "more supermarket", "reliance fresh", "reliance smart", "jiomart", "natures basket", "nature's basket",
    "spencers", "spencer's", "star bazaar", "ratnadeep", "24seven", "dunzo", "milkbasket", "country delight",
    # Shopping
    "amazon", "amazon pay", "flipkart", "myntra", "ajio", "nykaa", "meesho", "tata cliq", "croma", "reliance digital",
    "decathlon", "ikea", "lifestyle", "westside", "pantaloons", "max fashion", "reliance trends", "zara", "h&m",
    "lenskart", "tanishq", "caratlane", "firstcry", "pepperfry", "urban ladder", "boat", "apple", "samsung", "vijay sales",
    "urban company", "urbanclap",
    # Health
    "apollo", "apollo pharmacy", "apollo hospitals", "pharmeasy", "1mg", "tata 1mg", "netmeds", "medplus",
    "wellness forever", "fortis", "manipal", "narayana", "max healthcare", "practo", "thyrocare", "lal pathlabs",
    "dr lal pathlabs", "metropolis", "cult.fit", "cultfit", "healthifyme",
    # Transport & fuel
    "uber", "ola", "rapido", "indian oil", "iocl", "hpcl", "hp petrol", "bharat petroleum", "bpcl", "shell",
    "namma metro", "delhi metro", "dmrc", "mumbai metro", "bmrcl", "fastag", "park+", "yulu", "bounce",
    # Travel
    "irctc", "makemytrip", "goibibo", "indigo", "interglobe", "air india", "akasa", "vistara", "spicejet",
    "oyo", "airbnb", "cleartrip", "redbus", "yatra", "ixigo", "easemytrip", "booking.com", "agoda", "abhibus",
    # Entertainment & subscriptions
    "netflix", "prime video", "amazon prime", "hotstar", "jiohotstar", "disney", "spotify", "youtube", "google play",
    "bookmyshow", "pvr", "inox", "sonyliv", "sony liv", "zee5", "apple media", "apple services", "jiocinema",
    "audible", "gaana", "wynk",
    # Education
    "byjus", "byju's", "unacademy", "vedantu", "coursera", "udemy", "cuemath", "physics wallah", "upgrad",
    "great learning", "simplilearn", "kidzee", "eurokids",
    # Utilities, mobile & internet
    "bescom", "tata power", "adani electricity", "bses", "bses rajdhani", "bses yamuna", "msedcl", "mahadiscom",
    "wbsedcl", "tneb", "tangedco", "kseb", "cesc", "torrent power", "mahanagar gas", "indraprastha gas", "igl",
    "indane", "hp gas", "bharat gas", "bwssb", "mygate", "nobrokerhood", "airtel", "jio", "reliance jio",
    "vodafone", "vodafone idea", "vi", "bsnl", "mtnl", "act fibernet", "hathway", "tata play", "tata sky",
    "dish tv", "excitel",
    # Finance, investing, insurance, loans
    "zerodha", "zerodha broking", "groww", "upstox", "angel one", "angel broking", "5paisa", "dhan", "kuvera",
    "paytm money", "coin", "smallcase", "icici securities", "hdfc securities", "kotak securities", "motilal oswal",
    "bse", "nse", "bse star mf", "cams", "kfintech", "karvy", "nsdl", "cdsl", "indian clearing corp", "nps",
    "hdfc mutual fund", "icici prudential", "sbi mutual fund", "axis mutual fund", "mirae asset", "parag parikh",
    "ppfas", "nippon india", "uti mutual fund", "kotak mutual fund", "dsp", "quant",
    "lic", "hdfc life", "icici prudential life", "sbi life", "max life", "tata aig", "star health", "niva bupa",
    "care health", "bajaj allianz", "acko", "digit insurance", "policybazaar",
    "bajaj finance", "bajaj finserv", "tata capital", "lic housing", "muthoot", "manappuram", "home credit",
    "cred", "paytm", "phonepe", "google pay", "gpay", "bhim", "mobikwik", "freecharge", "razorpay", "cashfree",
    "billdesk", "payu", "ccavenue", "slice", "onecard", "simpl", "lazypay",
    # Government & tax
    "income tax", "income tax department", "nsdl tax", "tin-nsdl", "passport seva", "uidai", "epfo", "gst",
)
