package cz.obchodsken.parser

import java.text.Normalizer

enum class Category(val label: String, val emoji: String) {
    OVOCE_ZELENINA("Ovoce a zelenina", "🥦"),
    PECIVO("Pečivo", "🥖"),
    MASO_RYBY("Maso a ryby", "🥩"),
    UZENINY("Uzeniny", "🌭"),
    MLECNE("Mléčné výrobky a sýry", "🧀"),
    VEJCE("Vejce", "🥚"),
    MRAZENE("Mražené", "🧊"),
    TRVANLIVE("Trvanlivé potraviny", "🥫"),
    SLADKOSTI("Sladkosti a snacky", "🍫"),
    NAPOJE("Nápoje", "🥤"),
    ALKOHOL("Alkohol", "🍷"),
    DROGERIE("Drogerie a domácnost", "🧴"),
    ZVIRATA("Pro zvířata", "🐾"),
    OSTATNI("Ostatní", "📦");

    companion object {
        fun of(name: String?): Category = entries.firstOrNull { it.name == name } ?: OSTATNI
    }
}

data class ProductInfo(val name: String, val category: Category, val note: String? = null)

/**
 * Účtenky mají zkrácené názvy ("Odpad.pytle s uchy", "Kukuř.kuře.prs.ř.").
 * Tady se z nich dělá čitelný název + kategorie. Co tu chybí, se aplikace naučí z ručních oprav.
 */
object ProductNames {

    /** Klíč pro porovnávání: malá písmena, bez diakritiky a bez mezer kolem teček. */
    fun key(raw: String): String = stripDiacritics(raw.lowercase())
        .replace(Regex("""\s*\.\s*"""), ".")
        .replace(Regex("""\s+"""), " ")
        .trim()
        .trimEnd('.', ',', ':', ';', '*')
        .trim()

    fun stripDiacritics(s: String): String =
        Normalizer.normalize(s, Normalizer.Form.NFD).replace(Regex("""\p{Mn}+"""), "")

    // Celé názvy z Lidlu (klíč = key(raw)).
    private val exact: NameMatcher<ProductInfo> = NameMatcher(listOf(
        "Omáčka sladk.-kys" to ProductInfo("Omáčka sladkokyselá", Category.TRVANLIVE, "Asijská sladkokyselá omáčka"),
        "Odpad.pytle s uchy" to ProductInfo("Odpadkové pytle se zatahovacími uchy", Category.DROGERIE),
        "Odpad.pytle 35l" to ProductInfo("Odpadkové pytle 35 l", Category.DROGERIE),
        "Žervé s kápií" to ProductInfo("Žervé (čerstvý sýr) s kápií", Category.MLECNE),
        "Knäckebrot kukuř." to ProductInfo("Knäckebrot kukuřičný (křehký chléb)", Category.PECIVO),
        "Adriana Špagety" to ProductInfo("Špagety Adriana", Category.TRVANLIVE, "Těstoviny"),
        "Hrozny bílé 500gBS" to ProductInfo("Hroznové víno bílé bez semen 500 g", Category.OVOCE_ZELENINA),
        "Chléb dřevorubecký" to ProductInfo("Chléb dřevorubecký", Category.PECIVO),
        "Okurka salátová" to ProductInfo("Okurka salátová", Category.OVOCE_ZELENINA),
        "Tuňák celý v oleji" to ProductInfo("Tuňák v oleji (celé kousky)", Category.TRVANLIVE, "Konzerva"),
        "Rukavice" to ProductInfo("Rukavice", Category.DROGERIE),
        "Měkká utěrka" to ProductInfo("Měkká utěrka", Category.DROGERIE),
        "Bram.rané 5kg" to ProductInfo("Brambory rané 5 kg", Category.OVOCE_ZELENINA),
        "Bram.pozd. 5kg B" to ProductInfo("Brambory pozdní 5 kg (typ B)", Category.OVOCE_ZELENINA),
        "Tvaroh tučný 500g" to ProductInfo("Tvaroh tučný 500 g", Category.MLECNE),
        "Kakaový nápoj RFA" to ProductInfo("Kakaový nápoj (Rainforest Alliance)", Category.NAPOJE, "Instantní kakao"),
        "Banány 5ks" to ProductInfo("Banány 5 ks", Category.OVOCE_ZELENINA),
        "Treska bylinky-sýr" to ProductInfo("Treska s bylinkami a sýrem", Category.MASO_RYBY),
        "Rajčata keříková" to ProductInfo("Rajčata keříková", Category.OVOCE_ZELENINA),
        "Máslové sušenky" to ProductInfo("Máslové sušenky", Category.SLADKOSTI),
        "Třtinový cukr,500g" to ProductInfo("Třtinový cukr 500 g", Category.TRVANLIVE),
        "Chléb rustikální" to ProductInfo("Chléb rustikální", Category.PECIVO),
        "Čokoláda hořká" to ProductInfo("Čokoláda hořká", Category.SLADKOSTI),
        "Paprika bílá" to ProductInfo("Paprika bílá", Category.OVOCE_ZELENINA),
        "Vaflové kornouty" to ProductInfo("Vaflové kornouty (na zmrzlinu)", Category.SLADKOSTI),
        "Zahradní směs" to ProductInfo("Zahradní směs – mražená zelenina", Category.MRAZENE),
        "Filet z lososa" to ProductInfo("Filet z lososa", Category.MASO_RYBY),
        "Meloun vodní" to ProductInfo("Meloun vodní", Category.OVOCE_ZELENINA),
        "Jemný tav.sýr 150g" to ProductInfo("Jemný tavený sýr 150 g", Category.MLECNE),
        "Hoř. čokoláda,100g" to ProductInfo("Hořká čokoláda 100 g", Category.SLADKOSTI),
        "Čokoláda mléčná" to ProductInfo("Čokoláda mléčná", Category.SLADKOSTI),
        "Jemné tvarůžky" to ProductInfo("Olomoucké tvarůžky jemné", Category.MLECNE),
        "Pětizrnná švýcarka" to ProductInfo("Pětizrnná švýcarka (pečivo)", Category.PECIVO),
        "švýcarka dýňová" to ProductInfo("Švýcarka dýňová (pečivo)", Category.PECIVO),
        "Bio Baby špenát" to ProductInfo("Bio baby špenát", Category.OVOCE_ZELENINA),
        "Sauvignon Blanc" to ProductInfo("Víno Sauvignon Blanc", Category.ALKOHOL, "Bílé víno"),
        "Kostky ledu" to ProductInfo("Kostky ledu", Category.MRAZENE),
        "Popcorn slaný" to ProductInfo("Popcorn slaný", Category.SLADKOSTI),
        "Jog.smet.-stracc." to ProductInfo("Jogurt smetanový stracciatella", Category.MLECNE),
        "Inst.pol.zeleninov" to ProductInfo("Instantní polévka zeleninová", Category.TRVANLIVE),
        "Vídeňské párky" to ProductInfo("Vídeňské párky", Category.UZENINY),
        "Bivojova šunka" to ProductInfo("Bivojova šunka", Category.UZENINY),
        "Cottage Light" to ProductInfo("Cottage sýr light", Category.MLECNE),
        "Chléb horský" to ProductInfo("Chléb horský", Category.PECIVO),
        "Mozzarella" to ProductInfo("Mozzarella", Category.MLECNE),
        "Bramborový škrob" to ProductInfo("Bramborový škrob", Category.TRVANLIVE),
        "Čerstvé mléko 3,5%" to ProductInfo("Čerstvé mléko plnotučné 3,5 %", Category.MLECNE),
        "Čerstvé mléko 1,5%" to ProductInfo("Čerstvé mléko polotučné 1,5 %", Category.MLECNE),
        "Prací gel-barevné" to ProductInfo("Prací gel na barevné prádlo", Category.DROGERIE),
        "Bell Řepkový olej" to ProductInfo("Řepkový olej Bell", Category.TRVANLIVE),
        "Kukuř.kuře.prs.ř." to ProductInfo("Kukuřičné kuřecí prsní řízky", Category.MASO_RYBY),
        "Hrušky Lucas/Limon" to ProductInfo("Hrušky Lucas / Limonera", Category.OVOCE_ZELENINA),
        "Okrasne dyne kosik" to ProductInfo("Okrasné dýně v košíku (dekorace)", Category.OSTATNI),
        "Čok.s rozin.a oř." to ProductInfo("Čokoláda s rozinkami a oříšky", Category.SLADKOSTI),
        "Sedita Mila Retro" to ProductInfo("Mila Retro – oplatka (Sedita)", Category.SLADKOSTI),
        "Kuř. prsní filety" to ProductInfo("Kuřecí prsní filety", Category.MASO_RYBY),
        "Bramborové noky" to ProductInfo("Bramborové noky (gnocchi)", Category.TRVANLIVE),
        "Chléb lámankový" to ProductInfo("Chléb lámankový", Category.PECIVO),
        "Coca Cola Zero" to ProductInfo("Coca-Cola Zero", Category.NAPOJE),
        "Bagetka s párkem" to ProductInfo("Bagetka s párkem", Category.PECIVO, "Pečená bagetka s párkem"),
        "Kapsa třešňová" to ProductInfo("Kapsa třešňová (sladké pečivo)", Category.PECIVO),
        "Ovocná směs maliny" to ProductInfo("Ovocná směs s malinami – mražená", Category.MRAZENE),
    ))

    // Zkratky (klíč bez diakritiky, malými písmeny) -> plné slovo.
    private val abbreviations: Map<String, String> = mapOf(
        "odpad." to "odpadkové", "bram." to "brambory", "pozd." to "pozdní", "kukur." to "kukuřičné",
        "kure." to "kuřecí", "kur." to "kuřecí", "prs." to "prsní", "r." to "řízky", "tav." to "tavený",
        "hor." to "hořká", "cok." to "čokoláda", "rozin." to "rozinkami", "or." to "oříšky",
        "jog." to "jogurt", "smet." to "smetanový", "stracc." to "stracciatella", "inst." to "instantní",
        "pol." to "polévka", "zeleninov" to "zeleninová", "sladk." to "sladko", "mlec." to "mléčná",
        "cer." to "čerstvé", "vep." to "vepřové", "hov." to "hovězí", "uzen." to "uzená",
        "trv." to "trvanlivé", "polotuc." to "polotučné", "plnotuc." to "plnotučné", "nizkotuc." to "nízkotučný",
        "zel." to "zelenina", "mraz." to "mražené", "ovoc." to "ovocný", "jah." to "jahodový",
        "bil." to "bílý", "cerv." to "červené", "cerven." to "červené", "kys." to "kysané",
        "chl." to "chléb", "rohl." to "rohlík", "tous." to "toustový", "syr." to "sýr",
        "prac." to "prací", "mycí" to "mycí", "toal." to "toaletní", "pap." to "papír",
        "kapes." to "kapesníky", "ubrous." to "ubrousky", "nap." to "nápoj", "min." to "minerální",
        "perl." to "perlivá", "neperl." to "neperlivá", "jabl." to "jablečný", "pomer." to "pomerančový",
        "kys" to "kyselá", "bs" to "bez semen", "rfa" to "(Rainforest Alliance)", "bio" to "Bio",
        "ml" to "ml", "ks" to "ks",
    )

    // Kategorie podle klíčových slov (bez diakritiky). Pořadí je důležité – konkrétnější dřív.
    private val categoryKeywords: List<Pair<Category, List<String>>> = listOf(
        Category.ZVIRATA to listOf("granule", "kapsicka pro", "pro psy", "pro kocky", "steliv", "pamlsk"),
        Category.ALKOHOL to listOf("vino", "sauvignon", "chardonnay", "merlot", "cabernet", "rulandsk", "muller", "frankovk",
            "prosecco", "sekt", "pivo", "lezak", "lezák", "rum", "vodka", "gin ", "whisk", "slivovic", "becherov", "likér", "liker", "radler", "cider", "fernet"),
        Category.DROGERIE to listOf("pytl", "rukavic", "utěrk", "uterk", "praci", "aviváž", "avivaz", "mycí", "myci", "na nadobi", "toaletni", "papir",
            "kapesnik", "ubrous", "sampon", "mydlo", "sprchov", "zubni", "deodorant", "houbick", "cistic", "wc ", "folie", "alobal",
            "sacky", "svicka", "baterie", "zarovk", "tablety do", "vlhcene", "plenk", "vložky", "vlozky", "krem na", "holic"),
        Category.MRAZENE to listOf("mrazen", "zmrzlin", "nanuk", "kostky ledu", "pizza mraz", "hranolk"),
        Category.UZENINY to listOf("parky", "parek", "sunka", "salam", "klobas", "slanin", "uzen", "spekacek", "spekacky", "jatrov", "pastika", "kabanos", "debrecin"),
        Category.MASO_RYBY to listOf("kure", "kuřec", "kurec", "krut", "vepr", "hovez", "mlete", "maso", "rizek", "rizky", "filet", "losos",
            "tunak", "treska", "pstruh", "makrel", "sled", "kreve", "steak", "kotlet", "panenk", "krkovic", "stehn", "prsni"),
        Category.VEJCE to listOf("vejce", "vajec"),
        Category.MLECNE to listOf("mleko", "jogurt", "tvaroh", "syr", "mozzarell", "cottage", "maslo", "smetan", "zakys", "kefir", "podmasl",
            "eidam", "gouda", "hermelin", "niva", "parmez", "ricott", "mascarpon", "tvaruz", "zerve", "lucin", "pudink", "skyr", "cheddar", "feta", "balkan", "termix", "acidofil"),
        Category.PECIVO to listOf("chleb", "rohlik", "bageta", "bagetk", "kaiserk", "veka", "houska", "knackebrot", "toust", "kolac", "kapsa", "croissant",
            "loupak", "buchta", "koblih", "svycark", "dalamank", "tortill", "pecivo", "pletyn", "vanocka", "baget"),
        Category.SLADKOSTI to listOf("cokolad", "susenk", "oplat", "bonbon", " zele ", "gumov", "chips", "brambur", "popcorn", "tycink", "kornout",
            "dort", "keks", "perník", "pernik", "mila", "lizatk", "arasid", "orisky", "orech", "krekr", "slane tycinky", "musli tycink", "sladkost"),
        Category.NAPOJE to listOf("cola", "limonad", "dzus", "dzus", "voda", "mattoni", "kava", "caj", "napoj", "sirup", "nektar", "fanta", "sprite",
            "energy", "kakao", "kakaovy", "tonic", "smoothie", "juice"),
        Category.OVOCE_ZELENINA to listOf("rajc", "okurk", "paprik", "brambor", "cibul", "cesnek", "mrkev", "salat", "spenat", "zeli", "kvetak",
            "brokolic", "cuket", "dyne", "dyn ", "houby", "zampion", "jablk", "hrusk", "banan", "pomeran", "mandarin", "citron", "limet",
            "hrozn", "meloun", "jahod", "boruvk", "malin", "brosk", "merunk", "svestk", "kiwi", "ananas", "mango", "avokad", "grep",
            "redkvick", "rukol", "petrzel", "celer", "porek", "kedluben", "batat", "ovoce", "zelenin", "rane", "salat"),
        Category.TRVANLIVE to listOf("spaget", "testovin", "penne", "fusilli", "ryze", "mouka", "cukr", "sul", "olej", "ocet", "kecup", "horcic",
            "majonez", "omack", "polevk", "skrob", "konzerv", "fazol", "cocka", "hrach", "kukurice", "musli", "vlocky", "cornflakes",
            "med", "dzem", "marmelad", "nutell", "pomazank", "noky", "gnocchi", "kuskus", "bulgur", "kecup", "koreni", "bujon", "drozdi",
            "pecici", "kypric", "tunak", "sardink", "pesto", "protlak", "passata"),
    )

    /** Vrátí čitelný název a kategorii; [learned] = ručně opravené názvy (mají přednost). */
    fun describe(raw: String, learned: Map<String, ProductInfo> = emptyMap()): ProductInfo {
        val k = key(raw)
        learned[k]?.let { return it }
        exact.find(raw)?.let { return it }
        val expanded = expand(raw)
        return ProductInfo(expanded, categorize(expanded + " " + raw))
    }

    fun isKnown(raw: String): Boolean = exact.find(raw) != null

    fun expand(raw: String): String {
        // "Kukuř.kuře.prs.ř." -> ["Kukuř.", "kuře.", "prs.", "ř."]
        val tokens = Regex("""[^\s.,\-/]+\.?|[,\-/]""").findAll(raw).map { it.value }.toList()
        val out = mutableListOf<String>()
        for (t in tokens) {
            val k = stripDiacritics(t.lowercase())
            val rep = abbreviations[k]
            when {
                rep != null -> out += rep
                t == "-" || t == "/" -> out += t
                t == "," -> out += ","
                // "500gBS" -> "500 g BS"
                Regex("""^(\d+)(g|kg|ml|l|ks)(\p{L}*)$""", RegexOption.IGNORE_CASE).matches(t) -> {
                    val m = Regex("""^(\d+)(g|kg|ml|l|ks)(\p{L}*)$""", RegexOption.IGNORE_CASE).find(t)!!
                    out += m.groupValues[1] + " " + m.groupValues[2]
                    val rest = m.groupValues[3]
                    if (rest.isNotEmpty()) out += abbreviations[stripDiacritics(rest.lowercase())] ?: rest
                }
                else -> out += t
            }
        }
        val joined = out.joinToString(" ")
            .replace(" , ", ", ").replace(" ,", ",")
            .replace("sladko - kyselá", "sladkokyselá").replace("sladko - ", "sladko")
            .replace(Regex("""\s+-\s+"""), " – ")
            .replace(Regex("""\s+"""), " ")
            .trim()
        return joined.replaceFirstChar { it.uppercase() }
    }

    fun categorize(text: String): Category {
        val t = " " + stripDiacritics(text.lowercase()) + " "
        for ((cat, words) in categoryKeywords) {
            if (words.any { t.contains(stripDiacritics(it)) }) return cat
        }
        return Category.OSTATNI
    }

    /** Převod kategorií z Open Food Facts (en:...) na naše kategorie. */
    fun categoryFromOff(tags: List<String>, name: String): Category {
        val joined = tags.joinToString(" ").lowercase()
        val map = listOf(
            Category.ALKOHOL to listOf("alcoholic", "wines", "beers", "spirits"),
            Category.NAPOJE to listOf("beverages", "drinks", "waters", "sodas", "juices", "coffees", "teas"),
            Category.MRAZENE to listOf("frozen"),
            Category.MLECNE to listOf("dairies", "cheeses", "yogurts", "milks", "butters"),
            Category.UZENINY to listOf("sausages", "hams", "salamis", "prepared-meats"),
            Category.MASO_RYBY to listOf("meats", "fishes", "seafood", "poultry"),
            Category.SLADKOSTI to listOf("snacks", "chocolates", "sweets", "biscuits", "confectioneries", "candies", "chips"),
            Category.PECIVO to listOf("breads", "pastries", "viennoiseries"),
            Category.OVOCE_ZELENINA to listOf("fresh-vegetables", "fresh-fruits", "fruits", "vegetables"),
            Category.TRVANLIVE to listOf("pastas", "cereals", "sauces", "condiments", "oils", "sugars", "flours", "canned", "spreads", "groceries"),
        )
        for ((cat, keys) in map) if (keys.any { joined.contains(it) }) return cat
        return categorize(name)
    }

    /** Podobnost dvou názvů 0..1 – pro návrh propojení čárového kódu s položkou z účtenky. */
    fun similarity(a: String, b: String): Double {
        fun toks(s: String) = stripDiacritics(s.lowercase())
            .split(Regex("""[^a-z0-9]+""")).filter { it.length >= 3 }.map { it.take(5) }.toSet()
        val ta = toks(a)
        val tb = toks(b)
        if (ta.isEmpty() || tb.isEmpty()) return 0.0
        val inter = ta.count { x -> tb.any { y -> y.startsWith(x) || x.startsWith(y) } }
        return inter.toDouble() / minOf(ta.size, tb.size)
    }
}
