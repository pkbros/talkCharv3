export const PHONEME_TO_VISEME = {
    // Bilabials
    "p": "PP", "b": "PP", "m": "PP", "w": "OU",
    // Labiodentals
    "f": "FF", "v": "FF",
    // Dentals
    "θ": "TH", "ð": "TH",
    // Alveolars
    "t": "DD", "d": "DD", "n": "NN", "s": "SS", "z": "SS",
    "l": "NN", "ɾ": "DD",
    // Post-alveolars
    "ʃ": "CH", "ʒ": "CH", "tʃ": "CH", "dʒ": "CH",
    // Palatals
    "j": "II",
    // Velars
    "k": "KK", "ɡ": "KK", "ŋ": "KK",
    // Rhotics
    "r": "RR", "ɹ": "RR", "ɻ": "RR",
    // Glottals
    "h": "HH", "ʔ": "sil",
    // Short vowels
    "ɪ": "II", "ɛ": "EH", "æ": "AA", "ʌ": "AA",
    "ɑ": "AA", "ɒ": "AA", "ɔ": "OH", "ʊ": "OU",
    "ə": "AA", "ɐ": "AA",
    // Long vowels (ː already stripped or included)
    "iː": "II", "uː": "OU", "ɑː": "AA",
    "ɔː": "OH", "ɜː": "EH", "ɪː": "II",
    // Diphthongs — use start viseme, blend to end
    "eɪ": "EH", "aɪ": "AA", "ɔɪ": "OH",
    "aʊ": "AA", "oʊ": "OH", "ɪə": "II",
    "eə": "EH", "ʊə": "OU",
    // R-colored
    "ɚ": "EH", "ɝ": "EH",
    // Modifiers — strip before lookup
    "ː": null, "ˈ": null, "ˌ": null,
    // Silence
    "sp": "sil",
};