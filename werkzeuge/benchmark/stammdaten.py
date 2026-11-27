"""Stammdaten für den Generator: Namen, Anschriften, Versicherer, Tarife, Diagnosen, Berufe.

Alle Personen, Versicherer, Praxen und Firmen sind frei erfunden bzw. zufällig kombiniert.
Die Namenslisten decken bewusst die Vielfalt in Deutschland ab: häufige und seltene deutsche
Namen, Namen, die zugleich Alltagswörter sind (Sommer, Koch, Engel), Adelspartikel,
Doppelnamen, und Namen aus den großen Herkunftsgruppen (türkisch, polnisch, russlanddeutsch/
osteuropäisch, italienisch, griechisch, ex-jugoslawisch, rumänisch, arabisch, persisch/afghanisch,
kurdisch, vietnamesisch, chinesisch, west- und ostafrikanisch, indisch/pakistanisch, spanisch/
portugiesisch, französisch, niederländisch, skandinavisch, ungarisch, tschechisch, albanisch,
englisch) – mit Diakritika (ş ğ ı ç ł ż ś č ć š ž ő ű é à ñ å ø ț ș).
"""

# ----------------------------------------------------------------------
# Vornamen je Herkunft: (männlich, weiblich)
# ----------------------------------------------------------------------
VORNAMEN = {
    "de": (["Hans", "Peter", "Klaus", "Jürgen", "Uwe", "Wolfgang", "Dieter", "Günter", "Horst", "Manfred",
            "Thomas", "Michael", "Andreas", "Stefan", "Frank", "Matthias", "Christian", "Markus", "Jörg",
            "Ralf", "Sven", "Dirk", "Torsten", "Holger", "Lukas", "Leon", "Finn", "Jonas", "Elias", "Noah",
            "Paul", "Ben", "Felix", "Maximilian", "Moritz", "Tobias", "Florian", "Sebastian", "Kevin",
            "Dennis", "Benedikt", "Korbinian", "Gottfried", "Ottokar", "Friedhelm", "Volker", "Bernd",
            "Heinz-Josef", "Karl-Heinz", "Hans-Peter", "Ernst", "Detlef", "Rüdiger", "Wilfried", "Lennart",
            "Malte", "Jannik", "Till", "Emil", "Anton", "Theo", "Hannes", "Ole", "Fiete", "Jakob", "Johann"],
           ["Ursula", "Monika", "Sabine", "Petra", "Gabriele", "Renate", "Karin", "Brigitte", "Ingrid",
            "Andrea", "Claudia", "Susanne", "Birgit", "Stefanie", "Nicole", "Katrin", "Anja", "Silke",
            "Julia", "Anna", "Lena", "Laura", "Lea", "Mia", "Emma", "Hannah", "Sophie", "Marie", "Lina",
            "Clara", "Johanna", "Charlotte", "Frieda", "Greta", "Ida", "Paula", "Mathilda", "Henriette",
            "Hildegard", "Gertrud", "Waltraud", "Annegret", "Heike", "Doris", "Elke", "Jutta", "Dagmar",
            "Kerstin", "Mandy", "Jacqueline", "Chantal", "Annika", "Svenja", "Wiebke", "Imke", "Frauke",
            "Anna-Lena", "Marie-Luise", "Eva-Maria", "Rosemarie", "Liselotte", "Ilse", "Erika", "Vera"]),
    "tr": (["Mehmet", "Mustafa", "Ahmet", "Ali", "Hüseyin", "Hasan", "İbrahim", "Murat", "Emre", "Gökhan",
            "Serkan", "Volkan", "Ömer", "Yusuf", "Burak", "Cem", "Can", "Deniz", "Erdoğan", "Şükrü",
            "Oğuz", "Barış", "Tuğrul", "Çağlar", "Ilhan", "Kemal", "Orhan"],
           ["Ayşe", "Fatma", "Emine", "Hatice", "Zeynep", "Elif", "Merve", "Özlem", "Gülsen", "Songül",
            "Derya", "Tuğba", "Çiğdem", "Şeyma", "Büşra", "Esra", "Gizem", "Hülya", "Nur", "Sevgi",
            "İlknur", "Aylin", "Dilek", "Yasemin", "Gül"]),
    "pl": (["Łukasz", "Wojciech", "Paweł", "Grzegorz", "Michał", "Krzysztof", "Tomasz", "Piotr", "Jarosław",
            "Mirosław", "Zbigniew", "Bartłomiej", "Jakub", "Mateusz", "Andrzej", "Rafał"],
           ["Katarzyna", "Małgorzata", "Agnieszka", "Joanna", "Magdalena", "Monika", "Żaneta", "Bożena",
            "Grażyna", "Jadwiga", "Dorota", "Ewelina", "Justyna", "Urszula", "Weronika", "Zofia"]),
    "ru": (["Dmitri", "Sergej", "Wladimir", "Jewgenij", "Alexej", "Nikolai", "Andrej", "Juri", "Viktor",
            "Igor", "Oleg", "Artjom", "Maxim", "Waldemar", "Eduard", "Witali"],
           ["Olga", "Swetlana", "Natalia", "Tatjana", "Irina", "Jelena", "Oksana", "Ljudmila", "Anastasia",
            "Ekaterina", "Galina", "Walentina", "Nadeschda", "Xenia", "Alina", "Larissa"]),
    "it": (["Giuseppe", "Salvatore", "Luca", "Marco", "Francesco", "Antonio", "Giovanni", "Alessandro",
            "Matteo", "Nicolò", "Domenico", "Vincenzo"],
           ["Francesca", "Chiara", "Giulia", "Maria Grazia", "Rosaria", "Concetta", "Alessandra", "Federica",
            "Antonella", "Lucia", "Carmela", "Valentina"]),
    "gr": (["Georgios", "Dimitrios", "Konstantinos", "Ioannis", "Nikolaos", "Panagiotis", "Christos",
            "Vasileios"],
           ["Eleni", "Maria", "Aikaterini", "Vasiliki", "Sofia", "Georgia", "Despoina", "Paraskevi"]),
    "yu": (["Marko", "Dragan", "Zoran", "Goran", "Nikola", "Đorđe", "Emir", "Damir", "Ivan", "Stjepan",
            "Miloš", "Haris"],
           ["Ivana", "Jelena", "Mirela", "Amra", "Snežana", "Dragana", "Maja", "Lejla", "Željka", "Ana",
            "Vesna", "Dženana"]),
    "ro": (["Ionuț", "Mihai", "Ștefan", "Andrei", "Bogdan", "Cătălin", "Florin", "Răzvan"],
           ["Andreea", "Ioana", "Mihaela", "Alexandra", "Elena", "Cristina", "Roxana", "Bianca"]),
    "ar": (["Mohammed", "Ahmad", "Omar", "Khaled", "Samir", "Youssef", "Tarek", "Hamza", "Bilal",
            "Abdullah", "Karim", "Nabil"],
           ["Fatima", "Leila", "Rania", "Yasmin", "Amira", "Nour", "Samira", "Hanan", "Mariam", "Aisha",
            "Dalia", "Salma"]),
    "fa": (["Farid", "Reza", "Ali Reza", "Hamid", "Mehdi", "Navid", "Ahmad Shah", "Javad", "Babak",
            "Sohrab"],
           ["Mahnaz", "Shirin", "Parisa", "Laleh", "Nasrin", "Fereshteh", "Zahra", "Maryam", "Golnar",
            "Soraya"]),
    "ku": (["Azad", "Rojhat", "Dilshad", "Baran", "Serhat", "Zana"],
           ["Rojda", "Berivan", "Dilan", "Zozan", "Hêvî", "Nalin"]),
    "vi": (["Minh", "Tuan", "Duc", "Hung", "Quang", "Thanh", "Van An", "Long"],
           ["Lan", "Thi Mai", "Huong", "Linh", "Ngoc Anh", "Thu Trang", "Phuong", "Hoa"]),
    "zh": (["Wei", "Jun", "Hao", "Lei", "Jian", "Ming"],
           ["Li Na", "Xiaoling", "Mei", "Yan", "Jing", "Hui"]),
    "af": (["Kwame", "Kofi", "Chukwuemeka", "Oluwaseun", "Tesfay", "Abebe", "Mamadou", "Ousmane",
            "Emeka", "Yaw"],
           ["Ama", "Ngozi", "Adaeze", "Semhar", "Tigist", "Aminata", "Fatoumata", "Akosua", "Chiamaka",
            "Abena"]),
    "in": (["Rahul", "Venkatesh", "Arjun", "Sanjay", "Imran", "Faisal", "Rajesh", "Sivakumar"],
           ["Priya", "Ananya", "Lakshmi", "Deepika", "Ayesha", "Sana", "Kavitha", "Shreya"]),
    "es": (["José", "Juan Carlos", "Javier", "Joaquín", "João", "Rui", "Andrés", "Íñigo"],
           ["María", "Lucía", "Inês", "Begoña", "Ana Sofía", "Conceição", "Mónica", "Pilar"]),
    "fr": (["François", "Jérôme", "Étienne", "Benoît", "Loïc", "Mathéo"],
           ["Amélie", "Hélène", "Céline", "Chloé", "Anaïs", "Noémie"]),
    "nl": (["Joost", "Maarten", "Pieter", "Sjoerd", "Bram", "Daan"],
           ["Femke", "Annelies", "Marieke", "Sanne", "Lieke", "Roos"]),
    "sk": (["Søren", "Bjørn", "Lars", "Åke", "Henrik", "Jørgen"],
           ["Åsa", "Ingrid", "Sigrid", "Kirsten", "Mette", "Solveig"]),
    "hu": (["Zoltán", "Gergő", "Lőrinc", "István", "Ferenc", "Bálint"],
           ["Erzsébet", "Zsófia", "Réka", "Ildikó", "Krisztina", "Enikő"]),
    "cz": (["Jiří", "Tomáš", "Petr", "Lukáš", "Ondřej", "Radek"],
           ["Lucie", "Kateřina", "Tereza", "Zuzana", "Jitka", "Šárka"]),
    "al": (["Arben", "Driton", "Fatmir", "Besnik", "Valon", "Ilir"],
           ["Blerina", "Drita", "Arta", "Vjosa", "Mimoza", "Liridona"]),
    "en": (["Liam", "Patrick", "Sean", "James", "Oliver"],
           ["Siobhan", "Emily", "Charlotte", "Grace", "Olivia"]),
}

# ----------------------------------------------------------------------
# Nachnamen je Herkunft
# ----------------------------------------------------------------------
NACHNAMEN = {
    "de": ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz",
           "Hoffmann", "Schäfer", "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schröder", "Neumann",
           "Schwarz", "Zimmermann", "Braun", "Krüger", "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner",
           "Schmitz", "Krause", "Meier", "Lehmann", "Schmid", "Schulze", "Maier", "Köhler", "Herrmann",
           "König", "Walter", "Mayer", "Huber", "Kaiser", "Fuchs", "Peters", "Lang", "Scholz", "Möller",
           "Weiß", "Jung", "Hahn", "Schubert", "Vogel", "Friedrich", "Keller", "Günther", "Frank", "Berger",
           "Winkler", "Roth", "Beck", "Lorenz", "Baumann", "Franke", "Albrecht", "Schuster", "Simon",
           "Ludwig", "Böhm", "Winter", "Kraus", "Martin", "Schumacher", "Krämer", "Vogt", "Stein", "Jäger",
           "Otto", "Sommer", "Groß", "Seidel", "Heinrich", "Brandt", "Haas", "Schreiber", "Graf",
           "Schulte", "Dietrich", "Ziegler", "Kuhn", "Kühn", "Pohl", "Engel", "Horn", "Busch", "Bergmann",
           "Thomas", "Voigt", "Sauer", "Arnold", "Wolff", "Pfeiffer",
           # seltener
           "Ottersbach", "Quandt", "Rübsamen", "Würfel", "Pfannkuch", "Tschirner", "Ehrlich", "Liebig",
           "Wohlgemuth", "Kaltenbrunner", "Gottschalk", "Oelschläger", "Freitag", "Sonntag", "Meister",
           "Kurz", "Fröhlich", "Frisch", "Biedermann", "Hinterseer", "Zwirnmann", "Grünewald", "Eichhorn",
           "Habermann", "Kniep", "Lüdtke", "Steinbrück", "Ruppert", "Thalheim", "Uhlig", "Wendt", "Xylander",
           "Yorck", "Zeidler", "Aßmann", "Bräuer", "Dörfler", "Gößwein", "Häußler", "Kößler", "Löffler",
           "Nöth", "Rößner", "Schüßler", "Strauß", "Weißhaupt", "Prößl", "Haßelbeck", "Ühlein"],
    "tr": ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım", "Öztürk", "Aydın", "Özdemir",
           "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt", "Özkan", "Şimşek", "Polat",
           "Erdoğan", "Güneş", "Karaca", "Akgül", "Bayram", "Çakır", "Uğurlu", "Gündoğdu", "Ağaoğlu"],
    "pl": ["Kowalski", "Nowak", "Wiśniewski", "Wójcik", "Kowalczyk", "Kamiński", "Lewandowski", "Zieliński",
           "Szymański", "Woźniak", "Dąbrowski", "Kozłowski", "Jankowski", "Mazur", "Krawczyk", "Grabowski",
           "Pawłowski", "Michalski", "Król", "Wieczorek", "Jabłoński", "Stępień", "Kaźmierczak", "Żak",
           "Bąk", "Włodarczyk", "Sokołowski", "Kołodziej", "Przybył", "Gołębiowski"],
    "ru": ["Iwanow", "Petrow", "Smirnow", "Kusnezow", "Popow", "Wassiljew", "Sokolow", "Michailow",
           "Nowikow", "Fjodorow", "Morosow", "Wolkow", "Lebedew", "Semjonow", "Pawlow", "Koslow", "Orlow",
           "Saizew", "Schtscherbakow", "Tschernyschow", "Kudrjawzew", "Dück", "Penner", "Friesen", "Klassen",
           "Rempel", "Unruh", "Janzen", "Dyck", "Hildebrandt"],
    "it": ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci", "Marino",
           "Greco", "Bruno", "Gallo", "Conti", "De Luca", "Costa", "Giordano", "Mancini", "Rizzo", "Lombardi",
           "Moretti", "D'Angelo", "Caruso", "Santoro", "Lo Bianco", "Di Stefano"],
    "gr": ["Papadopoulos", "Georgiou", "Nikolaidis", "Konstantinidis", "Dimitriou", "Papageorgiou",
           "Ioannou", "Christodoulou", "Vasileiou", "Athanasiou", "Karagiannis", "Papadakis"],
    "yu": ["Horvat", "Kovačević", "Babić", "Marić", "Jurić", "Knežević", "Vuković", "Marković", "Petrović",
           "Nikolić", "Jovanović", "Đorđević", "Ilić", "Stojanović", "Hodžić", "Begić", "Mehmedović",
           "Hadžić", "Delić", "Šarić"],
    "ro": ["Popescu", "Ionescu", "Popa", "Constantin", "Dumitru", "Ștefănescu", "Munteanu", "Ciobanu",
           "Țurcanu", "Bălan"],
    "ar": ["Al-Hassan", "Haddad", "Khalil", "Nasser", "Abboud", "El-Masri", "Ibrahim", "Mansour",
           "Al-Rashid", "Saleh", "Hamdan", "Abu-Zaid", "Farouk", "El Amrani", "Benali"],
    "fa": ["Ahmadi", "Hosseini", "Karimi", "Rahimi", "Mohammadi", "Rezaei", "Hashemi", "Sadeghi", "Noori",
           "Haidari", "Popal", "Wardak", "Barakzai", "Tavakoli"],
    "ku": ["Aydemir", "Ekinci", "Tekin", "Baran", "Zana", "Bozkurt", "Ataş", "Kaplan"],
    "vi": ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Phan", "Vu", "Dang", "Bui", "Do", "Ngo", "Duong"],
    "zh": ["Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu", "Zhou", "Xu", "Sun"],
    "af": ["Mensah", "Owusu", "Boateng", "Okafor", "Adeyemi", "Nwosu", "Okonkwo", "Diallo", "Traoré",
           "Tesfaye", "Haile", "Abebe", "Mekonnen", "Osei", "Asante", "Koné", "Ndiaye", "Gebremedhin"],
    "in": ["Sharma", "Patel", "Singh", "Kumar", "Gupta", "Reddy", "Iyer", "Nair", "Krishnan", "Rao",
           "Khan", "Hussain", "Qureshi", "Malik", "Siddiqui", "Sivakumar"],
    "es": ["García", "Fernández", "González", "Rodríguez", "López", "Martínez", "Sánchez", "Pérez",
           "Muñoz", "Peña", "Núñez", "Silva", "Santos", "Ferreira", "Oliveira", "Gonçalves", "Conceição"],
    "fr": ["Dubois", "Lefèvre", "Moreau", "Girard", "Bonnet", "Mercier", "Rousseau", "Fontaine",
           "Chevalier", "Bérénger", "Faure", "Garnier"],
    "nl": ["de Vries", "van den Berg", "van Dijk", "Bakker", "Janssen", "Visser", "Smit", "de Jong",
           "Mulder", "van Leeuwen", "van der Meer", "Dekker"],
    "sk": ["Andersen", "Johansson", "Nilsson", "Larsen", "Sørensen", "Ågren", "Åberg", "Bjørnstad",
           "Lindqvist", "Østergaard"],
    "hu": ["Nagy", "Kovács", "Tóth", "Szabó", "Horváth", "Varga", "Kiss", "Molnár", "Németh", "Farkas",
           "Szűcs", "Kőváry", "Győri", "Pásztor"],
    "cz": ["Novák", "Svoboda", "Novotný", "Dvořák", "Černý", "Procházka", "Kučera", "Veselý", "Horák",
           "Růžička", "Kříž", "Šťastný", "Ševčík", "Bureš"],
    "al": ["Krasniqi", "Gashi", "Berisha", "Morina", "Hoxha", "Shala", "Bytyqi", "Kastrati", "Hasani"],
    "en": ["Smith", "O'Brien", "McDonald", "Murphy", "Walsh", "Taylor", "Kelly"],
}

# weibliche Formen (polnisch, russlanddeutsch, tschechisch)
WEIBLICHE_FORMEN = {
    "pl": lambda n: n[:-1] + "a" if n.endswith("ski") or n.endswith("cki") else n,
    "ru": lambda n: n + "a" if n.endswith(("ow", "ew", "in")) and n not in ("Dück",) else n,
    "cz": lambda n: (n[:-1] + "á" if n.endswith("ý") else n + "ová" if n[-1] not in "aeiouáéíóúůý" else n),
}

# Gewichte der Herkunftsgruppen (grob an der Bevölkerung orientiert, seltene Gruppen bewusst
# etwas häufiger, damit sie im Korpus vorkommen)
HERKUNFT_GEWICHTE = {"de": 46, "tr": 9, "pl": 6, "ru": 6, "it": 3, "gr": 2, "yu": 4, "ro": 3, "ar": 4,
                     "fa": 3, "ku": 2, "vi": 2, "zh": 1.5, "af": 2.5, "in": 2, "es": 2, "fr": 1, "nl": 1,
                     "sk": 1, "hu": 1.5, "cz": 1.5, "al": 2, "en": 1}

# Adelspartikel und Doppelnamen (deutsch)
ADELSNAMEN = ["von der Heyde", "von Bergen", "von Falkenhausen", "zu Dohna", "von und zu Gutenhag",
              "von Hohenfels", "von der Aue", "Freiherr von Rotenstein", "von Schönau", "von Stetten",
              "von Wolzogen-Brandt", "von Arnim-Lübbenau"]
DOPPEL_TEILE = ["Müller", "Lüdenscheidt", "Schmidt", "Hagedorn", "Krause", "Wegener", "Bachmann",
                "Riedel", "Pohlmann", "Kessler", "Seifert", "Brinkmann", "Yılmaz", "Nowak", "Rossi"]

TITEL = ["Dr.", "Dr. med.", "Prof. Dr.", "Dipl.-Ing.", "Dr. rer. nat.", "Dr. med. dent.", "Dr. jur.",
         "Dipl.-Kfm.", "Prof. Dr. med."]

# ----------------------------------------------------------------------
# Straßen und Orte
# ----------------------------------------------------------------------
STRASSEN = [
    "Hauptstraße", "Bahnhofstraße", "Am Alten Bahnhof", "Von-der-Tann-Str.", "Straße des 17. Juni",
    "Unter den Linden", "An der Alten Ziegelei", "Kurfürstendamm", "Berliner Allee", "Fürther Str.",
    "Lange Gasse", "Am Wehrdamm", "Im Winkel", "Auf dem Berge", "Zur Mühle", "Hinter der Kirche",
    "Alte Landstraße", "Konrad-Adenauer-Platz", "Graf-von-Galen-Str.", "St.-Johannis-Mühlgasse",
    "Theresienstraße", "Schweinauer Hauptstr.", "Marktplatz", "Ringstr.", "Mühlweg", "Kirchsteig",
    "Uferpromenade", "Rennweg", "Lindenallee", "Talstraße", "Wilhelm-Leuschner-Straße", "Alt-Moabit",
    "Kreuzberger Weg", "Goethestraße", "Schillerplatz", "Am Sonnenhang", "In den Gärten", "Gartenstr.",
    "Dr.-Martin-Luther-Ring", "Bgm.-Smidt-Str.", "Rosenstraße", "Ahornweg", "Birkenallee", "Eichendorffstr.",
    "Friedrich-Ebert-Damm", "Hohe Straße", "Kleine Bergstraße", "Neue Mainzer Str.", "Obere Hauptstr.",
    "Untere Grabenstraße", "Am Hang", "Auf der Höhe", "Zum Steinbruch", "Pfarrgasse", "Brunnenstraße",
    "Kastanienweg", "Lerchenfeldstraße", "Möhlstraße", "Nibelungenring", "Platz der Republik",
    "Am Stadtpark", "An den Eichen", "Feldkirchener Weg", "Hermann-Löns-Weg", "Industriestraße",
]

# (PLZ, Ort, Vorwahl ohne 0) – reale PLZ-Ort-Paare, viele mehrteilige Ortsnamen
ORTE = [
    ("90402", "Nürnberg", "911"), ("90762", "Fürth", "911"), ("91052", "Erlangen", "9131"),
    ("96047", "Bamberg", "951"), ("95444", "Bayreuth", "921"), ("93047", "Regensburg", "941"),
    ("86150", "Augsburg", "821"), ("80331", "München", "89"), ("60311", "Frankfurt am Main", "69"),
    ("15230", "Frankfurt (Oder)", "335"), ("61348", "Bad Homburg v. d. Höhe", "6172"),
    ("89231", "Neu-Ulm", "731"), ("66386", "St. Ingbert", "6894"), ("51429", "Bergisch Gladbach", "2204"),
    ("10117", "Berlin", "30"), ("20095", "Hamburg", "40"), ("50667", "Köln", "221"),
    ("40213", "Düsseldorf", "211"), ("70173", "Stuttgart", "711"), ("04109", "Leipzig", "341"),
    ("01067", "Dresden", "351"), ("30159", "Hannover", "511"), ("28195", "Bremen", "421"),
    ("45127", "Essen", "201"), ("44135", "Dortmund", "231"), ("53111", "Bonn", "228"),
    ("52062", "Aachen", "241"), ("48143", "Münster", "251"), ("33602", "Bielefeld", "521"),
    ("38100", "Braunschweig", "531"), ("34117", "Kassel", "561"), ("35390", "Gießen", "641"),
    ("99084", "Erfurt", "361"), ("07743", "Jena", "3641"), ("39104", "Magdeburg", "391"),
    ("14467", "Potsdam", "331"), ("18055", "Rostock", "381"), ("19053", "Schwerin", "385"),
    ("24103", "Kiel", "431"), ("23552", "Lübeck", "451"), ("21335", "Lüneburg", "4131"),
    ("83022", "Rosenheim", "8031"), ("87435", "Kempten (Allgäu)", "831"), ("88212", "Ravensburg", "751"),
    ("78462", "Konstanz", "7531"), ("79098", "Freiburg im Breisgau", "761"), ("68159", "Mannheim", "621"),
    ("69117", "Heidelberg", "6221"), ("76133", "Karlsruhe", "721"), ("66111", "Saarbrücken", "681"),
    ("67655", "Kaiserslautern", "631"), ("56068", "Koblenz", "261"), ("54290", "Trier", "651"),
    ("55116", "Mainz", "6131"), ("65183", "Wiesbaden", "611"), ("64283", "Darmstadt", "6151"),
    ("63065", "Offenbach am Main", "69"), ("97070", "Würzburg", "931"), ("97421", "Schweinfurt", "9721"),
    ("92637", "Weiden i.d.OPf.", "961"), ("94032", "Passau", "851"), ("84028", "Landshut", "871"),
    ("85049", "Ingolstadt", "841"), ("91126", "Schwabach", "9122"), ("91154", "Roth", "9171"),
    ("91207", "Lauf a.d.Pegnitz", "9123"), ("91301", "Forchheim", "9191"), ("96450", "Coburg", "9561"),
    ("95028", "Hof", "9281"), ("08056", "Zwickau", "375"), ("09111", "Chemnitz", "371"),
    ("02625", "Bautzen", "3591"), ("03046", "Cottbus", "355"), ("06108", "Halle (Saale)", "345"),
    ("06844", "Dessau-Roßlau", "340"), ("38440", "Wolfsburg", "5361"), ("31134", "Hildesheim", "5121"),
    ("26122", "Oldenburg", "441"), ("27568", "Bremerhaven", "471"), ("25813", "Husum", "4841"),
    ("17489", "Greifswald", "3834"), ("37073", "Göttingen", "551"), ("36037", "Fulda", "661"),
    ("57072", "Siegen", "271"), ("42103", "Wuppertal", "202"), ("47051", "Duisburg", "203"),
    ("45879", "Gelsenkirchen", "209"), ("44787", "Bochum", "234"), ("33098", "Paderborn", "5251"),
    ("49074", "Osnabrück", "541"), ("82319", "Starnberg", "8151"), ("82467", "Garmisch-Partenkirchen", "8821"),
    ("86899", "Landsberg am Lech", "8191"), ("89073", "Ulm", "731"), ("72070", "Tübingen", "7071"),
    ("73728", "Esslingen am Neckar", "711"), ("71634", "Ludwigsburg", "7141"), ("74072", "Heilbronn", "7131"),
    ("78050", "Villingen-Schwenningen", "7721"), ("63739", "Aschaffenburg", "6021"),
    ("99423", "Weimar", "3643"), ("07545", "Gera", "365"), ("02826", "Görlitz", "3581"),
    ("14776", "Brandenburg an der Havel", "3381"), ("27283", "Verden (Aller)", "4231"),
    ("22880", "Wedel", "4103"), ("24937", "Flensburg", "461"), ("18435", "Stralsund", "3831"),
    ("61440", "Oberursel (Taunus)", "6171"), ("65719", "Hofheim am Taunus", "6192"),
    ("57610", "Altenkirchen (Westerwald)", "2681"), ("53474", "Bad Neuenahr-Ahrweiler", "2641"),
    ("67433", "Neustadt an der Weinstraße", "6321"), ("76829", "Landau in der Pfalz", "6341"),
    ("66606", "St. Wendel", "6851"), ("83646", "Bad Tölz", "8041"), ("97980", "Bad Mergentheim", "7931"),
]

# Ausländische Anschriften (Straße, PLZ + Ort) – Kategorie "auslaendisch"
AUSLANDSADRESSEN = [
    ("Mariahilfer Straße 45/3", "A-1060 Wien"), ("Herrengasse 7", "8010 Graz"), ("Landstraße 12", "4020 Linz"),
    ("Bahnhofstrasse 12", "CH-8001 Zürich"), ("Spitalgasse 4", "3011 Bern"), ("Rue du Rhône 42", "1204 Genève"),
    ("Prinsengracht 263", "1016 GV Amsterdam"), ("Coolsingel 40", "3011 AD Rotterdam"),
    ("ul. Marszałkowska 10/12", "00-590 Warszawa"), ("ul. Długa 5", "80-827 Gdańsk"),
    ("Atatürk Cad. No: 12", "34000 İstanbul"), ("12 rue de la Paix", "75002 Paris"),
    ("Via Roma 15", "00184 Roma"), ("Calle Mayor 8", "28013 Madrid"), ("Váci utca 21", "1052 Budapest"),
    ("Vinohradská 48", "120 00 Praha 2"),
]

POSTFAECHER = ["Postfach 12 34 56", "Postfach 1234", "Postfach 10 01 21", "Postfach 31 07 45",
               "Postfach 80 05 61", "Postfach 2 20", "Postfach 66 01 13"]

ADRESSZUSAETZE = ["Hinterhaus, 2. OG", "App. 12", "3. Etage links", "Gartenhaus", "Whg. 7"]

# ----------------------------------------------------------------------
# Versicherer, Produkte, Banken (frei erfunden), echte Markennamen nur für Bestandslisten
# ----------------------------------------------------------------------
VERSICHERER = [
    # (Name, Kurzname, Sitz-PLZ, Sitz, Straße, Sparten-Schwerpunkt)
    ("Nordlicht Lebensversicherung AG", "Nordlicht", "20354", "Hamburg", "Ballindamm 17", "leben"),
    ("Rheintal Versicherung AG", "Rheintal", "50668", "Köln", "Theodor-Heuss-Ring 9", "sach"),
    ("Hanseatische Assekuranz VVaG", "Hanseatische", "28199", "Bremen", "Am Weserufer 3", "sach"),
    ("Alpenland Krankenversicherung a.G.", "Alpenland", "81675", "München", "Prinzregentenplatz 21", "kranken"),
    ("Mainfranken Versicherungsgruppe", "Mainfranken", "97082", "Würzburg", "Mainkai 4", "kfz"),
    ("Bodensee Allgemeine Versicherung AG", "Bodensee", "78467", "Konstanz", "Seestraße 50", "sach"),
    ("Weserbergland Rechtsschutz AG", "Weserbergland", "31785", "Hameln", "Deisterallee 1", "recht"),
    ("Elbtal Sachversicherung AG", "Elbtal", "01099", "Dresden", "Königsbrücker Str. 33", "sach"),
    ("Donau Leben AG", "Donau Leben", "93055", "Regensburg", "Donaustaufer Str. 100", "leben"),
    ("Ostsee Versicherungsverein a.G.", "Ostsee", "18057", "Rostock", "Am Strande 2", "kfz"),
    ("Fichtelgebirge Feuerkasse VVaG", "Fichtelgebirge", "95632", "Wunsiedel", "Marktplatz 6", "sach"),
    ("Schwarzwald Lebensversicherung AG", "Schwarzwald", "79100", "Freiburg im Breisgau", "Habsburgerstr. 8", "leben"),
    ("Harz Assekuranz AG", "Harz", "38855", "Wernigerode", "Breite Straße 70", "kfz"),
    ("Mosel Versicherung AG", "Mosel", "54292", "Trier", "Zurmaiener Str. 12", "sach"),
    ("Taunus Krankenversicherung AG", "Taunus", "61352", "Bad Homburg v. d. Höhe", "Kaiser-Friedrich-Promenade 4", "kranken"),
    ("Spreewald Pflegekasse VVaG", "Spreewald", "03222", "Lübbenau", "Ehm-Welk-Str. 2", "kranken"),
]
ECHTE_VERSICHERER_KURZ = ["Allianz", "HUK-COBURG", "ERGO", "AXA", "Debeka", "R+V", "Signal Iduna",
                          "Gothaer", "Generali", "Continentale", "Barmenia", "HanseMerkur", "LVM", "VHV",
                          "DEVK", "Württembergische", "Nürnberger", "Alte Leipziger", "Swiss Life",
                          "Canada Life", "Volkswohl Bund", "WWK", "Stuttgarter", "Zurich", "Helvetia",
                          "Provinzial", "DKV", "Hallesche", "die Bayerische"]

PRODUKTE = {
    "leben": ["VorsorgePlus Klassik", "RenteFlex 2020", "RisikoLeben Basis", "BU-Schutz Smart",
              "Basisrente Invest", "Riester-Rente Garant", "Kapital-Leben Premium"],
    "kranken": ["KomfortMed 300", "ZahnPlus 80", "PflegeTagegeld PT 50", "Krankentagegeld KT 43",
                "Stationär Plus 1-Bett", "AmbulantPlus Kompakt", "Beihilfeergänzung BE 20"],
    "sach": ["Haus&Heim Komfort", "PrivatHaftpflicht Best", "Hausrat Premium Plus", "Wohngebäude Exklusiv",
             "Glasschutz Basis", "Tierhalterhaftpflicht Hund"],
    "kfz": ["AutoSchutz Premium", "Kfz-Haftpflicht Kompakt", "Teilkasko Plus", "Vollkasko Komfort 300/150"],
    "recht": ["Rechtsschutz Familie Plus", "Verkehrsrechtsschutz Solo", "Arbeitsrechtsschutz Basis"],
}

BANKEN = ["Sparkasse Mittelfranken-Süd", "Volksbank Raiffeisenbank Oberland", "Kreissparkasse Talheim",
          "Stadtsparkasse Wiesenfeld", "VR-Bank Rhein-Lahn", "PSD Bank Nordwest", "Sparda-Bank Südwest",
          "Raiffeisenbank im Hügelland", "Commerzbank-Filiale Altstadt", "Postbank Ndl. Mitte"]

# ----------------------------------------------------------------------
# Medizin, Berufe, Arbeitgeber (Kategorie "erweitert")
# ----------------------------------------------------------------------
DIAGNOSEN = [
    "Essentielle (primäre) Hypertonie (I10.90)", "Diabetes mellitus, Typ 2 (E11.90)",
    "Lumboischialgie links (M54.4)", "Gonarthrose beidseits (M17.0)", "Depressive Episode, mittelgradig (F32.1)",
    "Asthma bronchiale (J45.9)", "Hypothyreose (E03.9)", "Vorhofflimmern, paroxysmal (I48.0)",
    "Migräne ohne Aura (G43.0)", "Bandscheibenvorfall L4/L5 (M51.2)", "Karpaltunnelsyndrom rechts (G56.0)",
    "Adipositas Grad I (E66.0)", "Chronische Gastritis (K29.5)", "Tinnitus aurium (H93.1)",
    "Allergische Rhinitis durch Pollen (J30.1)", "Hypercholesterinämie (E78.0)", "Anpassungsstörung (F43.2)",
    "Rotatorenmanschettenruptur rechts (M75.1)", "Parodontitis marginalis chronica (K05.3)",
    "Distale Radiusfraktur links (S52.5)", "Distorsion des oberen Sprunggelenks (S93.40)",
    "Osteoporose ohne Fraktur (M81.0)", "Psoriasis vulgaris (L40.0)", "Obstruktives Schlafapnoe-Syndrom (G47.31)",
    "Koronare Herzkrankheit, Ein-Gefäß-Erkrankung (I25.11)", "Generalisierte Angststörung (F41.1)",
]
MEDIKAMENTE = ["Ramipril 5 mg 1-0-0", "Metformin 1000 mg 1-0-1", "L-Thyroxin 75 µg 1-0-0",
               "Ibuprofen 600 mg bei Bedarf", "Pantoprazol 20 mg 1-0-0", "Sertralin 50 mg 1-0-0",
               "Bisoprolol 2,5 mg 1-0-0", "Atorvastatin 20 mg 0-0-1", "Salbutamol-Spray bei Bedarf"]
BERUFE = ["Dachdecker", "Gesundheits- und Krankenpflegerin", "Softwareentwickler", "Polier",
          "Steuerfachangestellte", "selbstständige Physiotherapeutin", "Erzieherin", "Kfz-Mechatroniker",
          "Lehrerin (verbeamtet)", "Rechtsanwalt", "Industriekauffrau", "Busfahrer", "Zahnärztin",
          "Elektroniker für Betriebstechnik", "Altenpflegehelferin", "Maschinenbauingenieur", "Verkäuferin",
          "Lagerist", "Bankkaufmann", "Friseurmeisterin", "Polizeivollzugsbeamter", "Landwirt", "Architektin",
          "Schreiner", "Medizinische Fachangestellte", "IT-Systemadministrator", "Sozialpädagogin", "Koch",
          "Fliesenleger", "Hebamme", "Berufskraftfahrer", "Pharmareferentin"]
ARBEITGEBER = ["Dachbau Krämer GmbH & Co. KG", "Klinikum am Rosengarten gGmbH", "Stadtwerke Talheim GmbH",
               "Kreissparkasse Oberland", "Bäckerei Hofmeister", "Logistikzentrum Frankenland GmbH",
               "Grundschule am Wiesengrund", "Metallbau Yıldız GmbH", "Pflegedienst Sonnenschein e.V.",
               "Autohaus Lindner GmbH", "Softwarehaus Nordstern AG", "Elektro Schuster e.K.",
               "Gemeinschaftspraxis am Schlossplatz", "Spedition Brandauer GmbH", "Seniorenstift Abendrot",
               "Brauerei Kesselring KG", "Maschinenfabrik Ostertal AG", "Kita Pusteblume"]

STAATSANGEHOERIGKEIT = {"de": "deutsch", "tr": "türkisch", "pl": "polnisch", "ru": "deutsch", "it": "italienisch",
                        "gr": "griechisch", "yu": "kroatisch", "ro": "rumänisch", "ar": "syrisch",
                        "fa": "afghanisch", "ku": "türkisch", "vi": "vietnamesisch", "zh": "chinesisch",
                        "af": "ghanaisch", "in": "indisch", "es": "spanisch", "fr": "französisch",
                        "nl": "niederländisch", "sk": "dänisch", "hu": "ungarisch", "cz": "tschechisch",
                        "al": "kosovarisch", "en": "irisch"}
GEBURTSORTE = ["Gelsenkirchen", "Ankara", "Gdańsk", "Karaganda", "Palermo", "Thessaloniki", "Sarajevo",
               "Timișoara", "Damaskus", "Herat", "Diyarbakır", "Hanoi", "Shenyang", "Kumasi", "Hyderabad",
               "Sevilla", "Lyon", "Utrecht", "Aarhus", "Debrecen", "Brno", "Prishtina", "Cork",
               "Hoyerswerda", "Wolfsburg", "Rosenheim", "Neubrandenburg", "Zwickau"]
KONFESSIONEN = ["römisch-katholisch", "evangelisch-lutherisch", "islamisch", "konfessionslos",
                "griechisch-orthodox", "neuapostolisch"]

# ----------------------------------------------------------------------
# Kfz
# ----------------------------------------------------------------------
FAHRZEUGE = ["VW Golf VIII 1.5 eTSI", "Opel Astra K 1.2", "BMW 320d Touring", "Skoda Octavia Combi 2.0 TDI",
             "Ford Focus Turnier", "Mercedes-Benz C 200", "Toyota Yaris Hybrid", "Renault Clio V",
             "Hyundai i30", "Fiat 500e", "Seat Leon ST", "Dacia Duster", "Tesla Model 3", "Audi A4 Avant"]
UNFALLARTEN = ["Auffahrunfall", "Parkschaden", "Vorfahrtsverletzung", "Spurwechselunfall", "Wildunfall",
               "Glasbruch durch Steinschlag", "Hagelschaden", "Rückwärtsfahren auf Parkplatz"]
POLIZEI = ["Polizeiinspektion Nürnberg-Süd", "Polizeirevier Mitte", "Polizeistation Erlangen-Land",
           "Polizeipräsidium Oberfranken", "Autobahnpolizei Feucht"]

# ----------------------------------------------------------------------
# Kliniken, Praxen, Mail-Anbieter
# ----------------------------------------------------------------------
KLINIKEN = ["Klinikum Nordstadt", "Kreisklinik am Wald", "Krankenhaus St. Ansgar", "Universitätsklinik Talheim",
            "Fachklinik Bergblick", "Rehazentrum Am Kurpark"]
APOTHEKEN = ["Apotheke am Markt", "Löwen-Apotheke", "Stern-Apotheke", "Rathaus-Apotheke", "Linden-Apotheke"]
FACHRICHTUNGEN = ["Facharzt für Innere Medizin", "Fachärztin für Allgemeinmedizin", "Facharzt für Orthopädie",
                  "Fachärztin für Dermatologie", "Zahnarzt", "Fachärztin für Neurologie",
                  "Facharzt für Hals-Nasen-Ohren-Heilkunde", "Psychologische Psychotherapeutin"]
MAILANBIETER = ["web.de", "gmx.de", "t-online.de", "gmail.com", "outlook.de", "posteo.de", "freenet.de",
                "yahoo.de", "icloud.com", "mailbox.org", "gmx.net", "arcor.de"]

# Betreffzeilen-Themen für Briefe
BRIEF_ANLAESSE = ["ablauf", "beitragsanpassung", "jahresgespraech", "regulierung", "adressaenderung",
                  "nachweis", "beratung"]
