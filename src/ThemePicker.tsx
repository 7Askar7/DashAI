import { useLayoutEffect, useState } from 'react';
import { Check } from 'lucide-react';

const themes = [
  ['violet', 'Фиолетовый', '#b9a6ff'], ['blue', 'Синий', '#acc6ff'],
  ['cyan', 'Бирюзовый', '#8fe1ec'], ['emerald', 'Изумрудный', '#90e5bb'],
  ['amber', 'Янтарный', '#f4cc89'], ['rose', 'Розовый', '#ffb0cf'],
] as const;

export default function ThemePicker() {
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem('dashai.theme');
      return themes.find(([id]) => id === saved)?.[0] ?? 'violet';
    } catch { return 'violet'; }
  });
  const [warning, setWarning] = useState('');
  useLayoutEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  return <fieldset className="theme-picker">
    <legend>Цвет PRISM <span>{themes.find(([id]) => id === theme)?.[1]}</span></legend>
    <div className="theme-swatches">
      {themes.map(([id, label, color]) => <label key={id} title={label} style={{ color }}>
        <input type="radio" name="prism-theme" value={id} aria-label={label} checked={theme === id} onChange={() => {
          setTheme(id);
          try { localStorage.setItem('dashai.theme', id); setWarning(''); }
          catch { setWarning('Цвет изменён. Сохранение в этом браузере недоступно.'); }
        }}/>
        <span className="theme-swatch" aria-hidden="true">{theme === id && <Check size={14}/>}</span>
      </label>)}
    </div>
    {warning && <p role="status">{warning}</p>}
  </fieldset>;
}
