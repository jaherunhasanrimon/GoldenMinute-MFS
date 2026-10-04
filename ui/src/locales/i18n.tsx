import React, { createContext, useContext, useState, useEffect } from 'react';
import enTranslations from './en.json';
import bnTranslations from './bn.json';

type Language = 'en' | 'bn';

interface I18nContextType {
  lang: Language;
  setLang: (lang: Language) => void;
  toggleLang: () => void;
  t: (path: string) => string;
}

const translations: Record<Language, any> = {
  en: enTranslations,
  bn: bnTranslations,
};

const I18nContext = createContext<I18nContextType | undefined>(undefined);

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [lang, setLangState] = useState<Language>(() => {
    const saved = localStorage.getItem('gm_lang');
    return (saved === 'en' || saved === 'bn') ? saved : 'bn';
  });

  const setLang = (newLang: Language) => {
    setLangState(newLang);
    localStorage.setItem('gm_lang', newLang);
    document.documentElement.lang = newLang;
  };

  const toggleLang = () => {
    setLang(lang === 'en' ? 'bn' : 'en');
  };

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const t = (path: string): string => {
    const keys = path.split('.');
    let current = translations[lang];
    for (const key of keys) {
      if (current && typeof current === 'object' && key in current) {
        current = current[key];
      } else {
        return path;
      }
    }
    return typeof current === 'string' ? current : path;
  };

  return (
    <I18nContext.Provider value={{ lang, setLang, toggleLang, t }}>
      {children}
    </I18nContext.Provider>
  );
};

export const useI18n = () => {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within an I18nProvider');
  }
  return context;
};
